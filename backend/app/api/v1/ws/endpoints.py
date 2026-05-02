"""
WebSocket API 端点
"""

import asyncio
import json
import logging
from secrets import token_hex

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.trade_schemas import WSMessage

from .manager import (
    MAX_CONNECTIONS_PER_IP,
    MAX_CONNECTIONS_PER_USER,
    MAX_GLOBAL_CONNECTIONS,
    manager,
)
from .proxies import (
    _VALID_KLINE_INTERVALS,
    BinanceWSProxy,
    HuobiProxy,
    OKXProxy,
    PollingFallback,
    _parse_kline_interval,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_HEARTBEAT_INTERVAL = 30  # 客户端 30s 无消息视为断连
_AUTH_TIMEOUT = 5.0
_HEARTBEAT_GRACE_PERIOD = 10.0
_AUTH_PROTOCOL_PREFIX = "access_token."


def _normalize_channels(channels: list[str], interval: str) -> list[str]:
    """将 kline 频道与 interval 合并为 kline_<interval>（issue #5）"""
    result: list[str] = []
    for ch in channels:
        if ch == "kline":
            norm_interval = interval if interval in _VALID_KLINE_INTERVALS else "1m"
            result.append(f"kline_{norm_interval}")
        elif ch.startswith("kline_") and _parse_kline_interval(ch) != "1m":
            result.append(ch)
        else:
            result.append(ch)
    return result


def _parse_subprotocols(websocket: WebSocket) -> list[str]:
    """解析客户端请求的 Sec-WebSocket-Protocol 列表。"""
    raw = websocket.headers.get("sec-websocket-protocol", "")
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _select_accept_subprotocol(websocket: WebSocket) -> str | None:
    """选择一个可回显给客户端的子协议。"""
    protocols = _parse_subprotocols(websocket)
    if not protocols:
        return None
    for protocol in protocols:
        if not protocol.startswith(_AUTH_PROTOCOL_PREFIX):
            return protocol
    return protocols[0]


def _read_protocol_token(websocket: WebSocket) -> str | None:
    """从 Sec-WebSocket-Protocol 中提取 access token。"""
    for protocol in _parse_subprotocols(websocket):
        if protocol.startswith(_AUTH_PROTOCOL_PREFIX):
            return protocol.removeprefix(_AUTH_PROTOCOL_PREFIX)
    return None


async def _read_auth_token(websocket: WebSocket) -> str | None:
    """从 Authorization header 或首条 auth 消息中提取 Token（issue #2）

    - 优先检查 HTTP 升级请求中的 Authorization: Bearer <token> header
    - 降级到 WebSocket 首条 auth 消息（向后兼容）
    """
    # 优先：Authorization header
    auth_header = websocket.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]

    protocol_token = _read_protocol_token(websocket)
    if protocol_token:
        return protocol_token

    # 降级：等待首条 auth 消息
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=_AUTH_TIMEOUT)
        cmd = json.loads(raw)
        if cmd.get("action") == "auth":
            return cmd.get("token", "")
    except TimeoutError:
        pass
    except Exception:
        pass
    return None


def _is_pong_message(raw: str) -> bool:
    """兼容 action/type 两种 pong 消息格式。"""
    try:
        cmd = json.loads(raw)
    except Exception:
        return False
    return cmd.get("action") == "pong" or cmd.get("type") == "pong"


async def _probe_heartbeat(websocket: WebSocket, conn_id: str) -> tuple[bool, str | None]:
    """发送业务层 ping，并等待客户端在宽限期内回复 pong。

    若客户端在宽限期内发来其他业务消息，则把该消息交还主循环继续处理。
    """
    await websocket.send_text(WSMessage(type="ping", data={}).model_dump_json())
    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=_HEARTBEAT_GRACE_PERIOD,
        )
    except TimeoutError:
        logger.warning("[WS] 心跳无响应，关闭连接 %s", conn_id)
        await websocket.close(code=4000, reason="Heartbeat timeout")
        return False, None
    except WebSocketDisconnect:
        return False, None

    if _is_pong_message(raw):
        return True, None
    return True, raw


async def _verify_connection(websocket: WebSocket) -> tuple[str, str] | None:
    """认证并校验连接限制，成功返回 (user_id, conn_id)，失败返回 None 并已 close"""
    token = await _read_auth_token(websocket)
    if not token:
        await websocket.close(code=4001, reason="Authentication required")
        return None

    try:
        from app.core.security import verify_token

        payload = verify_token(token, token_type="access")
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=4001, reason="Invalid token")
            return None
    except Exception as e:
        logger.warning("[WSAuth] Authentication failed: %s", e)
        await websocket.close(code=4001, reason="Authentication failed")
        return None

    client_ip = websocket.client.host if websocket.client else "unknown"

    if manager.get_global_connection_count() >= MAX_GLOBAL_CONNECTIONS:
        await websocket.close(code=4003, reason="Server busy, too many connections")
        return None

    if manager.get_ip_connection_count(client_ip) >= MAX_CONNECTIONS_PER_IP:
        await websocket.close(
            code=4002, reason=f"Too many connections from your IP (max {MAX_CONNECTIONS_PER_IP})"
        )
        return None

    if manager.get_user_connection_count(user_id) >= MAX_CONNECTIONS_PER_USER:
        await websocket.close(
            code=4002, reason=f"Too many connections (max {MAX_CONNECTIONS_PER_USER})"
        )
        return None

    conn_id = manager.generate_conn_id()
    manager.register(conn_id, websocket, user_id, client_ip)
    return user_id, conn_id


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


@router.websocket("/market")
async def ws_market(websocket: WebSocket):
    accept_subprotocol = _select_accept_subprotocol(websocket)
    await websocket.accept(subprotocol=accept_subprotocol)

    result = await _verify_connection(websocket)
    if result is None:
        return
    user_id, conn_id = result

    initial_symbol = websocket.query_params.get("symbol", "BTCUSDT").upper()
    initial_exchange = websocket.query_params.get("exchange", "binance").lower()
    initial_market = websocket.query_params.get("market", "spot").lower()
    if initial_market not in ("spot", "perp"):
        initial_market = "spot"

    manager.subscribe(conn_id, ["ticker"], [initial_symbol], market_type=initial_market)

    proxy = manager._proxies.get(initial_exchange)
    if proxy:
        await proxy.start_if_needed("ticker", initial_symbol, market_type=initial_market)
    else:
        logger.warning(
            "[WS] 交易所 %s 的代理未注册，连接 %s 无法接收实时推送",
            initial_exchange,
            conn_id,
        )

    try:
        nonce = token_hex(16)
        await websocket.send_text(
            WSMessage(
                type="connected",
                data={
                    "connection_id": conn_id,
                    "subscribed": initial_symbol,
                    "exchange": initial_exchange,
                    "market": initial_market,
                    "nonce": nonce,
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
            raw: str | None = None
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=_HEARTBEAT_INTERVAL)
            except TimeoutError:
                # 超时后先主动发 ping，再等待客户端的业务层 pong
                alive, pending_raw = await _probe_heartbeat(websocket, conn_id)
                if not alive:
                    break
                if pending_raw is None:
                    continue
                raw = pending_raw

            cmd = json.loads(raw)
            action = cmd.get("action", "")

            if action == "ping":
                await websocket.send_text(WSMessage(type="pong", data={}).model_dump_json())
            elif action == "subscribe":
                channels = cmd.get("channels", ["ticker"])
                symbols = cmd.get("symbols", [initial_symbol])
                exchange = cmd.get("exchange", initial_exchange)
                market = cmd.get("market", initial_market)
                interval = cmd.get("interval", "1m")
                if market not in ("spot", "perp"):
                    market = "spot"

                normalized = _normalize_channels(channels, interval)
                manager.subscribe(conn_id, normalized, symbols, market_type=market)

                p = manager._proxies.get(exchange)
                if p:
                    for ch in normalized:
                        for sym in symbols:
                            await p.start_if_needed(ch, sym, market_type=market)
                else:
                    logger.warning(
                        "[WS] 交易所 %s 的代理未注册，连接 %s 订阅 %s/%s 将无实时数据",
                        exchange,
                        conn_id,
                        channels,
                        symbols,
                    )
                await websocket.send_text(
                    WSMessage(
                        type="subscribed",
                        data={"channels": normalized, "symbols": symbols, "market": market},
                    ).model_dump_json()
                )
            elif action == "unsubscribe":
                channels = cmd.get("channels", ["ticker"])
                symbols = cmd.get("symbols", [])
                market = cmd.get("market", initial_market)
                interval = cmd.get("interval", "1m")
                if market not in ("spot", "perp"):
                    market = "spot"

                normalized = _normalize_channels(channels, interval)
                manager.unsubscribe(conn_id, normalized, symbols, market_type=market)

                for p in manager._proxies.values():
                    for ch in normalized:
                        for sym in symbols:
                            await p.stop_if_idle(ch, sym, market_type=market)
                await websocket.send_text(
                    WSMessage(
                        type="unsubscribed",
                        data={"channels": normalized, "symbols": symbols, "market": market},
                    ).model_dump_json()
                )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("[WS] 异常: %s: %s", conn_id, exc)
    finally:
        await manager.unregister(conn_id)


async def init_ws_proxies():
    """初始化 WebSocket 交易所代理（issue #8）"""
    try:
        import websockets  # noqa: F401

        manager.register_proxy("binance", BinanceWSProxy(manager))
        manager.register_proxy("okx", OKXProxy(manager))
        manager.register_proxy("huobi", HuobiProxy(manager))
        logger.info("[WSProxy] WebSocket 代理全部注册成功")
    except ImportError:
        logger.warning(
            "[WSProxy] websockets 库不可用，降级为 PollingFallback 轮询模式"
        )
        polling = PollingFallback(manager)
        await polling.start()
    except Exception as exc:
        logger.error("[WSProxy] 代理初始化异常: %s，降级为轮询", exc)
        polling = PollingFallback(manager)
        await polling.start()


async def cleanup_ws_proxies():
    for proxy in manager._proxies.values():
        if hasattr(proxy, "_tasks"):
            for task in proxy._tasks.values():
                task.cancel()
    manager._subs.clear()
