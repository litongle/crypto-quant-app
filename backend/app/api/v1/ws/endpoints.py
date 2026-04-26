"""
WebSocket API 端点
"""
import json
import logging
import time
import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.trade_schemas import WSMessage
from .manager import manager, Subscription
from .proxies import BinanceWSProxy, OKXProxy, HuobiProxy, PollingFallback

logger = logging.getLogger(__name__)
router = APIRouter()

@router.websocket("/market")
async def ws_market(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
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

    user_conn_count = sum(1 for sub in manager._subs.values() if sub.user_id == user_id)
    if user_conn_count >= 5:
        await websocket.close(code=4002, reason="Too many connections (max 5)")
        return

    await websocket.accept()
    conn_id = f"conn-{id(websocket)}-{int(time.time()*1000)}"
    manager.register(conn_id, websocket, user_id)

    initial_symbol = websocket.query_params.get("symbol", "BTCUSDT").upper()
    initial_exchange = websocket.query_params.get("exchange", "binance").lower()
    manager.subscribe(conn_id, ["ticker"], [initial_symbol])

    proxy = manager._proxies.get(initial_exchange)
    if proxy: await proxy.start_if_needed("ticker", initial_symbol)

    try:
        await websocket.send_text(WSMessage(
            type="connected",
            data={"connection_id": conn_id, "subscribed": initial_symbol, "exchange": initial_exchange},
        ).model_dump_json())

        async with httpx.AsyncClient(timeout=5.0) as client:
            ticker_data = await _fetch_initial_ticker(client, initial_symbol, initial_exchange)
            if ticker_data:
                await websocket.send_text(WSMessage(
                    type="ticker", exchange=initial_exchange, symbol=initial_symbol, data=ticker_data,
                ).model_dump_json())

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
                manager.subscribe(conn_id, channels, symbols)
                p = manager._proxies.get(exchange)
                if p:
                    for ch in channels:
                        for sym in symbols: await p.start_if_needed(ch, sym)
                await websocket.send_text(WSMessage(type="subscribed", data={"channels": channels, "symbols": symbols}).model_dump_json())
            elif action == "unsubscribe":
                channels = cmd.get("channels", ["ticker"])
                symbols = cmd.get("symbols", [])
                manager.unsubscribe(conn_id, channels, symbols)
                for p in manager._proxies.values():
                    for ch in channels:
                        for sym in symbols: await p.stop_if_idle(ch, sym)
                await websocket.send_text(WSMessage(type="unsubscribed", data={"channels": channels, "symbols": symbols}).model_dump_json())
    except WebSocketDisconnect: pass
    except Exception as exc: logger.error("[WS] 异常: %s: %s", conn_id, exc)
    finally: manager.unregister(conn_id)

async def _fetch_initial_ticker(client, symbol, exchange):
    try:
        if exchange == "binance":
            resp = await client.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}")
            d = resp.json()
            return {"symbol": symbol, "price": d.get("lastPrice", "0"), "price_change_percent": d.get("priceChangePercent", "0")}
        elif exchange == "okx":
            inst_id = f"{symbol[:-4]}-{symbol[-4:]}" if symbol.endswith("USDT") else symbol
            resp = await client.get(f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}")
            t = resp.json().get("data", [{}])[0]
            return {"symbol": symbol, "price": t.get("last", "0"), "price_change_percent": t.get("changeUtc24h", "0")}
        elif exchange == "huobi":
            resp = await client.get(f"https://api.huobi.pro/market/detail/merged?symbol={symbol.lower()}")
            tick = resp.json().get("tick", {})
            return {"symbol": symbol, "price": str(tick.get("close", 0))}
    except Exception: return None

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
            for task in proxy._tasks.values(): task.cancel()
    manager._subs.clear()
