"""
WebSocket API 端点
"""

import asyncio
import json
import logging

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.trade_schemas import WSMessage

from .manager import manager
from .proxies import BinanceWSProxy, HuobiProxy, OKXProxy, PollingFallback

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/market")
async def ws_market(websocket: WebSocket):
    await websocket.accept()
    conn_id = manager.generate_conn_id()
    client_ip = websocket.client.host if websocket.client else "unknown"

    # 等待首条 auth 消息（Token 不再走 URL，防止泄露到日志/Referer）
    token = ""
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        cmd = json.loads(raw)
        if cmd.get("action") == "auth":
            token = cmd.get("token", "")
    except TimeoutError:
        await websocket.close(code=4001, reason="Authentication timeout")
        return
    except Exception:
        pass

    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    try:
        from app.core.security import verify_token

        payload = verify_token(token, token_type="access")
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=4001, reason="Invalid token")
            return
    except Exception as e:
        logger.warning("[WSAuth] Authentication failed: %s", e)
        await websocket.close(code=4001, reason="Authentication failed")
        return

    # 检查连接数限制
    from app.api.v1.ws.manager import (
        MAX_CONNECTIONS_PER_IP,
        MAX_CONNECTIONS_PER_USER,
        MAX_GLOBAL_CONNECTIONS,
    )

    if manager.get_global_connection_count() >= MAX_GLOBAL_CONNECTIONS:
        await websocket.close(code=4003, reason="Server busy, too many connections")
        return

    if manager.get_ip_connection_count(client_ip) >= MAX_CONNECTIONS_PER_IP:
        await websocket.close(
            code=4002, reason=f"Too many connections from your IP (max {MAX_CONNECTIONS_PER_IP})"
        )
        return

    if manager.get_user_connection_count(user_id) >= MAX_CONNECTIONS_PER_USER:
        await websocket.close(
            code=4002, reason=f"Too many connections (max {MAX_CONNECTIONS_PER_USER})"
        )
        return

    manager.register(conn_id, websocket, user_id, client_ip)

    initial_symbol = websocket.query_params.get("symbol", "BTCUSDT").upper()
    initial_exchange = websocket.query_params.get("exchange", "binance").lower()
    initial_market = websocket.query_params.get("market", "spot").lower()
    if initial_market not in ("spot", "perp"):
        initial_market = "spot"
    manager.subscribe(conn_id, ["ticker"], [initial_symbol])

    proxy = manager._proxies.get(initial_exchange)
    if proxy:
        await proxy.start_if_needed("ticker", initial_symbol, market_type=initial_market)

    try:
        await websocket.send_text(
            WSMessage(
                type="connected",
                data={
                    "connection_id": conn_id,
                    "subscribed": initial_symbol,
                    "exchange": initial_exchange,
                    "market": initial_market,
                },
            ).model_dump_json()
        )

        async with httpx.AsyncClient(timeout=5.0) as client:
            ticker_data = await _fetch_initial_ticker(
                client,
                initial_symbol,
                initial_exchange,
                initial_market,
            )
            if ticker_data:
                await websocket.send_text(
                    WSMessage(
                        type="ticker",
                        exchange=initial_exchange,
                        symbol=initial_symbol,
                        data=ticker_data,
                    ).model_dump_json()
                )

        while True:
            raw = await websocket.receive_text()
            cmd = json.loads(raw)
            action = cmd.get("action", "")

            if action == "ping":
                await websocket.send_text(WSMessage(type="pong", data={}).model_dump_json())
            elif action == "subscribe":
                channels = cmd.get("channels", ["ticker"])
                symbols = cmd.get("symbols", [initial_symbol])
                exchange = cmd.get("exchange", initial_exchange)
                market = cmd.get("market", initial_market)
                if market not in ("spot", "perp"):
                    market = "spot"
                manager.subscribe(conn_id, channels, symbols)
                p = manager._proxies.get(exchange)
                if p:
                    for ch in channels:
                        for sym in symbols:
                            await p.start_if_needed(ch, sym, market_type=market)
                await websocket.send_text(
                    WSMessage(
                        type="subscribed",
                        data={"channels": channels, "symbols": symbols, "market": market},
                    ).model_dump_json()
                )
            elif action == "unsubscribe":
                channels = cmd.get("channels", ["ticker"])
                symbols = cmd.get("symbols", [])
                market = cmd.get("market", initial_market)
                if market not in ("spot", "perp"):
                    market = "spot"
                manager.unsubscribe(conn_id, channels, symbols)
                for p in manager._proxies.values():
                    for ch in channels:
                        for sym in symbols:
                            await p.stop_if_idle(ch, sym, market_type=market)
                await websocket.send_text(
                    WSMessage(
                        type="unsubscribed",
                        data={"channels": channels, "symbols": symbols, "market": market},
                    ).model_dump_json()
                )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("[WS] 异常: %s: %s", conn_id, exc)
    finally:
        manager.unregister(conn_id)


async def _fetch_initial_ticker(client, symbol, exchange, market_type="spot"):
    """初始拉一次 ticker, 给 WS 客户端立即推送一条"""
    try:
        if exchange == "binance":
            host = "fapi.binance.com/fapi/v1" if market_type == "perp" else "api.binance.com/api/v3"
            resp = await client.get(f"https://{host}/ticker/24hr?symbol={symbol}")
            d = resp.json()
            return {
                "symbol": symbol,
                "price": d.get("lastPrice", "0"),
                "price_change_percent": d.get("priceChangePercent", "0"),
            }
        elif exchange == "okx":
            inst_id = f"{symbol[:-4]}-{symbol[-4:]}" if symbol.endswith("USDT") else symbol
            if market_type == "perp":
                inst_id = f"{inst_id}-SWAP"
            resp = await client.get(f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}")
            t = resp.json().get("data", [{}])[0]
            return {
                "symbol": symbol,
                "price": t.get("last", "0"),
                "price_change_percent": t.get("changeUtc24h", "0"),
            }
        elif exchange == "huobi":
            if market_type == "perp":
                # contract_code: BTCUSDT → BTC-USDT
                code = f"{symbol[:-4]}-{symbol[-4:]}" if symbol.endswith("USDT") else symbol
                resp = await client.get(
                    f"https://futures.htx.com/linear-swap-ex/market/detail/merged?contract_code={code}"
                )
            else:
                resp = await client.get(
                    f"https://api.huobi.pro/market/detail/merged?symbol={symbol.lower()}"
                )
            tick = resp.json().get("tick", {})
            return {"symbol": symbol, "price": str(tick.get("close", 0))}
    except Exception:
        return None


async def init_ws_proxies():
    try:
        import websockets

        manager.register_proxy("binance", BinanceWSProxy(manager))
        manager.register_proxy("okx", OKXProxy(manager))
        manager.register_proxy("huobi", HuobiProxy(manager))
    except ImportError:
        polling = PollingFallback(manager)
        await polling.start()


async def cleanup_ws_proxies():
    for proxy in manager._proxies.values():
        if hasattr(proxy, "_tasks"):
            for task in proxy._tasks.values():
                task.cancel()
    manager._subs.clear()
