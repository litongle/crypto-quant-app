"""
WebSocket 行情推送模块

架构：
- WSRouter: 管理 WebSocket 连接 + 订阅关系
- ExchangeWSProxy: 代理交易所 WebSocket（Binance/OKX），统一格式转发
- 前端连接 /ws/market 即可订阅实时行情

支持的频道:
- ticker: 实时价格推送
- kline: K线更新推送
- orderbook: 订单簿深度推送

前端协议:
- 订阅: {"action": "subscribe", "channels": ["ticker"], "symbols": ["BTCUSDT", "ETHUSDT"]}
- 取消: {"action": "unsubscribe", "channels": ["ticker"], "symbols": ["BTCUSDT"]}
- 心跳: {"action": "ping"}  → 回复 {"type": "pong"}

连接地址: ws://localhost:8000/api/v1/ws/market
"""
import asyncio
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.trade_schemas import (
    KlineSchema,
    OrderBookSchema,
    TickerSchema,
    WSMessage,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== 订阅管理 ====================

@dataclass
class Subscription:
    """单个 WebSocket 连接的订阅信息"""
    channels: set[str] = field(default_factory=set)  # ticker/kline/orderbook
    symbols: set[str] = field(default_factory=set)    # BTCUSDT/ETHUSDT/...
    ws: WebSocket | None = None


class WSConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        # connection_id → Subscription
        self._subs: dict[str, Subscription] = {}
        # (channel, symbol) → set[connection_id]
        self._routing: dict[tuple[str, str], set[str]] = defaultdict(set)
        # 交易所 WS 代理引用（后续注入）
        self._proxies: dict[str, "ExchangeWSProxy"] = {}

    def register(self, conn_id: str, ws: WebSocket) -> None:
        self._subs[conn_id] = Subscription(ws=ws)
        logger.info("[WSManager] 连接注册: %s, 当前连接数: %d", conn_id, len(self._subs))

    def unregister(self, conn_id: str) -> None:
        sub = self._subs.pop(conn_id, None)
        if sub:
            # 清理路由表
            for channel in sub.channels:
                for symbol in sub.symbols:
                    key = (channel, symbol)
                    self._routing[key].discard(conn_id)
                    if not self._routing[key]:
                        del self._routing[key]
            logger.info("[WSManager] 连接注销: %s, 剩余连接数: %d", conn_id, len(self._subs))

    def subscribe(self, conn_id: str, channels: list[str], symbols: list[str]) -> None:
        sub = self._subs.get(conn_id)
        if not sub:
            return
        for ch in channels:
            sub.channels.add(ch)
            for sym in symbols:
                sym_upper = sym.upper()
                sub.symbols.add(sym_upper)
                self._routing[(ch, sym_upper)].add(conn_id)
        logger.info(
            "[WSManager] 订阅: conn=%s, channels=%s, symbols=%s",
            conn_id, channels, symbols,
        )

    def unsubscribe(self, conn_id: str, channels: list[str], symbols: list[str]) -> None:
        sub = self._subs.get(conn_id)
        if not sub:
            return
        for ch in channels:
            for sym in symbols:
                sym_upper = sym.upper()
                key = (ch, sym_upper)
                self._routing[key].discard(conn_id)
                if not self._routing[key]:
                    del self._routing[key]
            # 如果 symbols 为空，取消整个 channel
            if not symbols:
                for sym in list(sub.symbols):
                    key = (ch, sym)
                    self._routing[key].discard(conn_id)
                    if not self._routing[key]:
                        del self._routing[key]
        logger.info(
            "[WSManager] 取消订阅: conn=%s, channels=%s, symbols=%s",
            conn_id, channels, symbols,
        )

    def get_subscribers(self, channel: str, symbol: str) -> list[WebSocket]:
        """获取某频道某 symbol 的所有活跃 WebSocket"""
        conn_ids = self._routing.get((channel, symbol.upper()), set())
        result = []
        for cid in conn_ids:
            sub = self._subs.get(cid)
            if sub and sub.ws:
                result.append(sub.ws)
        return result

    def has_subscribers(self, channel: str, symbol: str) -> bool:
        return bool(self._routing.get((channel, symbol.upper())))

    def register_proxy(self, exchange: str, proxy: "ExchangeWSProxy") -> None:
        self._proxies[exchange] = proxy

    @property
    def connection_count(self) -> int:
        return len(self._subs)


# 全局管理器
manager = WSConnectionManager()


# ==================== 交易所 WS 代理 ====================

class ExchangeWSProxy:
    """交易所 WebSocket 代理基类

    作用：
    - 后台连接交易所 WebSocket
    - 接收原始数据，统一格式后推送到 WSConnectionManager
    - 仅在有订阅者时才连接，无人订阅时自动断开
    """

    EXCHANGE: str = ""

    def __init__(self, conn_manager: WSConnectionManager):
        self._manager = conn_manager
        self._tasks: dict[str, asyncio.Task] = {}  # symbol → task
        self._running = False

    async def start_if_needed(self, channel: str, symbol: str) -> None:
        """如果有订阅者则启动对应 WS 连接"""
        key = f"{channel}:{symbol}"
        if key in self._tasks:
            return
        if self._manager.has_subscribers(channel, symbol):
            self._tasks[key] = asyncio.create_task(
                self._run_stream(channel, symbol),
                name=f"ws-proxy-{self.EXCHANGE}-{key}",
            )
            logger.info("[WSProxy-%s] 启动: %s", self.EXCHANGE, key)

    async def stop_if_idle(self, channel: str, symbol: str) -> None:
        """如果无订阅者则停止"""
        key = f"{channel}:{symbol}"
        if not self._manager.has_subscribers(channel, symbol):
            task = self._tasks.pop(key, None)
            if task:
                task.cancel()
                logger.info("[WSProxy-%s] 停止: %s (无订阅者)", self.EXCHANGE, key)

    async def _run_stream(self, channel: str, symbol: str) -> None:
        """子类实现：连接交易所 WS 并推送数据"""
        raise NotImplementedError

    async def _broadcast(self, msg: WSMessage) -> None:
        """推送到所有订阅者"""
        subscribers = self._manager.get_subscribers(msg.type, msg.symbol or "")
        for ws in subscribers:
            try:
                await ws.send_text(msg.model_dump_json())
            except Exception:
                pass  # 连接可能已断开，由主循环清理


class BinanceWSProxy(ExchangeWSProxy):
    """Binance WebSocket 代理

    Binance 现货 WS:
    - ticker: wss://stream.binance.com/ws/<symbol>@ticker
    - kline:   wss://stream.binance.com/ws/<symbol>@kline_<interval>
    - depth:   wss://stream.binance.com/ws/<symbol>@depth20@100ms
    """

    EXCHANGE = "binance"
    BASE_WS_URL = "wss://stream.binance.com/ws"

    async def _run_stream(self, channel: str, symbol: str) -> None:
        symbol_lower = symbol.lower()
        if channel == "ticker":
            stream = f"{symbol_lower}@ticker"
        elif channel == "kline":
            stream = f"{symbol_lower}@kline_1m"
        elif channel == "orderbook":
            stream = f"{symbol_lower}@depth20@100ms"
        else:
            return

        url = f"{self.BASE_WS_URL}/{stream}"

        try:
            async with httpx.AsyncClient() as client:
                # 使用 httpx 的 WebSocket（需要 httpx[http2] 或用 websockets 库）
                # 这里用 websockets 作为底层 ws 客户端
                import websockets
                async with websockets.connect(url, ping_interval=20) as ws:
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                            msg = self._parse_message(data, channel, symbol)
                            if msg:
                                await self._broadcast(msg)
                        except json.JSONDecodeError:
                            pass
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            logger.debug("[BinanceWS] 解析异常: %s", exc)
        except asyncio.CancelledError:
            logger.info("[BinanceWS] 连接关闭: %s/%s", channel, symbol)
        except Exception as exc:
            logger.warning("[BinanceWS] 连接异常: %s/%s: %s", channel, symbol, exc)
            # 5 秒后重连
            await asyncio.sleep(5)
            if self._manager.has_subscribers(channel, symbol):
                key = f"{channel}:{symbol}"
                self._tasks.pop(key, None)
                await self.start_if_needed(channel, symbol)

    def _parse_message(self, data: dict, channel: str, symbol: str) -> WSMessage | None:
        if channel == "ticker" and "c" in data:
            return WSMessage(
                type="ticker",
                exchange="binance",
                symbol=symbol,
                data={
                    "symbol": symbol,
                    "price": data.get("c", "0"),
                    "price_change": data.get("p", "0"),
                    "price_change_percent": data.get("P", "0"),
                    "high_24h": data.get("h", "0"),
                    "low_24h": data.get("l", "0"),
                    "volume_24h": data.get("v", "0"),
                    "quote_volume_24h": data.get("q", "0"),
                },
            )
        elif channel == "kline" and "k" in data:
            k = data["k"]
            return WSMessage(
                type="kline",
                exchange="binance",
                symbol=symbol,
                data={
                    "symbol": symbol,
                    "open": k.get("o", "0"),
                    "high": k.get("h", "0"),
                    "low": k.get("l", "0"),
                    "close": k.get("c", "0"),
                    "volume": k.get("v", "0"),
                    "is_closed": k.get("x", False),
                },
            )
        elif channel == "orderbook" and "b" in data:
            return WSMessage(
                type="orderbook",
                exchange="binance",
                symbol=symbol,
                data={
                    "bids": [{"price": p, "quantity": q} for p, q in data.get("b", [])[:20]],
                    "asks": [{"price": p, "quantity": q} for p, q in data.get("a", [])[:20]],
                },
            )
        return None


class OKXWSProxy(ExchangeWSProxy):
    """OKX WebSocket 代理

    OKX V5 WS:
    - wss://ws.okx.com:8443/ws/v5/public
    - 订阅: {"op": "subscribe", "args": [{"channel": "tickers", "instId": "BTC-USDT"}]}
    """

    EXCHANGE = "okx"
    WS_URL = "wss://ws.okx.com:8443/ws/v5/public"

    async def _run_stream(self, channel: str, symbol: str) -> None:
        # BTCUSDT → BTC-USDT
        inst_id = self._to_inst_id(symbol)
        okx_channel = {"ticker": "tickers", "kline": "candle1m", "orderbook": "books5"}.get(channel)
        if not okx_channel:
            return

        sub_msg = json.dumps({
            "op": "subscribe",
            "args": [{"channel": okx_channel, "instId": inst_id}],
        })

        try:
            import websockets
            async with websockets.connect(self.WS_URL, ping_interval=20) as ws:
                await ws.send(sub_msg)
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                        if "data" in data:
                            msg = self._parse_message(data, channel, symbol)
                            if msg:
                                await self._broadcast(msg)
                    except json.JSONDecodeError:
                        pass
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.debug("[OKXWS] 解析异常: %s", exc)
        except asyncio.CancelledError:
            logger.info("[OKXWS] 连接关闭: %s/%s", channel, symbol)
        except Exception as exc:
            logger.warning("[OKXWS] 连接异常: %s/%s: %s", channel, symbol, exc)
            await asyncio.sleep(5)
            if self._manager.has_subscribers(channel, symbol):
                key = f"{channel}:{symbol}"
                self._tasks.pop(key, None)
                await self.start_if_needed(channel, symbol)

    def _to_inst_id(self, symbol: str) -> str:
        stablecoins = ("USDT", "USDC", "BUSD")
        for sc in stablecoins:
            if symbol.endswith(sc):
                base = symbol[:-len(sc)]
                return f"{base}-{sc}"
        return symbol

    def _parse_message(self, data: dict, channel: str, symbol: str) -> WSMessage | None:
        okx_channel = data.get("arg", {}).get("channel", "")
        items = data.get("data", [])
        if not items:
            return None

        if okx_channel == "tickers":
            t = items[0]
            return WSMessage(
                type="ticker",
                exchange="okx",
                symbol=symbol,
                data={
                    "symbol": symbol,
                    "price": t.get("last", "0"),
                    "price_change_percent": t.get("changeUtc24h", "0"),
                    "high_24h": t.get("high24h", "0"),
                    "low_24h": t.get("low24h", "0"),
                    "volume_24h": t.get("vol24h", "0"),
                    "quote_volume_24h": t.get("volCcy24h", "0"),
                },
            )
        elif okx_channel.startswith("candle"):
            k = items[0]
            return WSMessage(
                type="kline",
                exchange="okx",
                symbol=symbol,
                data={
                    "symbol": symbol,
                    "open": k[1] if len(k) > 1 else "0",
                    "high": k[2] if len(k) > 2 else "0",
                    "low": k[3] if len(k) > 3 else "0",
                    "close": k[4] if len(k) > 4 else "0",
                    "volume": k[5] if len(k) > 5 else "0",
                },
            )
        elif okx_channel == "books5":
            b = items[0]
            return WSMessage(
                type="orderbook",
                exchange="okx",
                symbol=symbol,
                data={
                    "bids": [{"price": p, "quantity": q} for p, q, *_ in b.get("bids", [])[:20]],
                    "asks": [{"price": p, "quantity": q} for p, q, *_ in b.get("asks", [])[:20]],
                },
            )
        return None


class HuobiWSProxy(ExchangeWSProxy):
    """Huobi WebSocket 代理

    火币 WebSocket:
    - wss://api.huobi.pro/ws
    - 订阅: {"sub": "market.btcusdt.ticker"}
    - 数据是 gzip 压缩的，需要解压
    """

    EXCHANGE = "huobi"
    WS_URL = "wss://api.huobi.pro/ws"

    async def _run_stream(self, channel: str, symbol: str) -> None:
        symbol_lower = symbol.lower()
        if channel == "ticker":
            sub_topic = f"market.{symbol_lower}.detail"
        elif channel == "kline":
            sub_topic = f"market.{symbol_lower}.kline.1min"
        elif channel == "orderbook":
            sub_topic = f"market.{symbol_lower}.depth.step0"
        else:
            return

        sub_msg = json.dumps({"sub": sub_topic, "id": f"sub-{symbol_lower}"})

        try:
            import websockets
            import gzip
            async with websockets.connect(self.WS_URL, ping_interval=20) as ws:
                await ws.send(sub_msg)
                async for raw in ws:
                    try:
                        # 火币 WS 返回 gzip 压缩数据
                        if isinstance(raw, bytes):
                            decompressed = gzip.decompress(raw).decode("utf-8")
                        else:
                            decompressed = raw

                        data = json.loads(decompressed)

                        # 心跳响应
                        if "ping" in data:
                            pong = {"pong": data["ping"]}
                            await ws.send(json.dumps(pong))
                            continue

                        # 订阅确认
                        if "subbed" in data:
                            logger.info("[HuobiWS] 订阅成功: %s", data.get("subbed"))
                            continue

                        if "ch" in data:
                            msg = self._parse_message(data, channel, symbol)
                            if msg:
                                await self._broadcast(msg)
                    except json.JSONDecodeError:
                        pass
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.debug("[HuobiWS] 解析异常: %s", exc)
        except asyncio.CancelledError:
            logger.info("[HuobiWS] 连接关闭: %s/%s", channel, symbol)
        except Exception as exc:
            logger.warning("[HuobiWS] 连接异常: %s/%s: %s", channel, symbol, exc)
            await asyncio.sleep(5)
            if self._manager.has_subscribers(channel, symbol):
                key = f"{channel}:{symbol}"
                self._tasks.pop(key, None)
                await self.start_if_needed(channel, symbol)

    def _parse_message(self, data: dict, channel: str, symbol: str) -> WSMessage | None:
        ch = data.get("ch", "")
        tick = data.get("tick", {})

        if not tick:
            return None

        if "detail" in ch or channel == "ticker":
            return WSMessage(
                type="ticker",
                exchange="huobi",
                symbol=symbol,
                data={
                    "symbol": symbol,
                    "price": str(tick.get("close", "0")),
                    "price_change_percent": str(tick.get("change", "0")),
                    "high_24h": str(tick.get("high", "0")),
                    "low_24h": str(tick.get("low", "0")),
                    "volume_24h": str(tick.get("vol", "0")),
                    "quote_volume_24h": str(tick.get("amount", "0")),
                },
            )
        elif "kline" in ch or channel == "kline":
            k = tick
            return WSMessage(
                type="kline",
                exchange="huobi",
                symbol=symbol,
                data={
                    "symbol": symbol,
                    "open": str(k.get("open", "0")),
                    "high": str(k.get("high", "0")),
                    "low": str(k.get("low", "0")),
                    "close": str(k.get("close", "0")),
                    "volume": str(k.get("vol", "0")),
                },
            )
        elif "depth" in ch or channel == "orderbook":
            return WSMessage(
                type="orderbook",
                exchange="huobi",
                symbol=symbol,
                data={
                    "bids": [{"price": p, "quantity": q} for p, q in tick.get("bids", [])[:20]],
                    "asks": [{"price": p, "quantity": q} for p, q in tick.get("asks", [])[:20]],
                },
            )
        return None


# ==================== 轮询降级模式 ====================

class PollingFallback:
    """WebSocket 不可用时的轮询降级

    当 websockets 库未安装或交易所 WS 不可用时，
    使用 REST 轮询方式推送行情数据。
    """

    def __init__(self, conn_manager: WSConnectionManager):
        self._manager = conn_manager
        self._tasks: dict[str, asyncio.Task] = {}
        self._running = False

    async def start(self) -> None:
        """启动轮询"""
        if self._running:
            return
        self._running = True
        self._tasks["polling"] = asyncio.create_task(self._poll_loop(), name="ws-polling-fallback")
        logger.info("[PollingFallback] 轮询降级模式启动")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()

    async def _poll_loop(self) -> None:
        """每 2 秒轮询一次 ticker"""
        from app.core.exchange_adapter import BinanceAdapter

        while self._running:
            try:
                # 收集所有被订阅的 symbol
                symbols: set[str] = set()
                for sub in self._manager._subs.values():
                    symbols.update(sub.symbols)

                if not symbols:
                    await asyncio.sleep(2)
                    continue

                # 批量获取行情
                adapter = BinanceAdapter("", "")
                for symbol in list(symbols)[:10]:  # 最多 10 个
                    try:
                        ticker = await adapter.get_ticker(symbol)
                        msg = WSMessage(
                            type="ticker",
                            exchange="binance",
                            symbol=symbol,
                            data=TickerSchema.from_dataclass(ticker).model_dump(),
                        )
                        await self._broadcast(msg)
                    except Exception:
                        pass

                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[PollingFallback] 轮询异常: %s", exc)
                await asyncio.sleep(5)

    async def _broadcast(self, msg: WSMessage) -> None:
        subscribers = self._manager.get_subscribers(msg.type, msg.symbol or "")
        for ws in subscribers:
            try:
                await ws.send_text(msg.model_dump_json())
            except Exception:
                pass


# ==================== WebSocket 端点 ====================

@router.websocket("/market")
async def ws_market(websocket: WebSocket):
    """WebSocket 行情推送端点

    协议:
    - 连接: ws://localhost:8000/api/v1/ws/market?symbol=BTCUSDT&exchange=binance
    - 订阅: {"action": "subscribe", "channels": ["ticker"], "symbols": ["BTCUSDT"]}
    - 取消: {"action": "unsubscribe", "channels": ["ticker"], "symbols": ["BTCUSDT"]}
    - 心跳: {"action": "ping"}
    """
    await websocket.accept()
    conn_id = f"conn-{id(websocket)}-{int(time.time()*1000)}"
    manager.register(conn_id, websocket)

    # 从 query params 读取初始订阅
    initial_symbol = websocket.query_params.get("symbol", "BTCUSDT").upper()
    initial_exchange = websocket.query_params.get("exchange", "binance").lower()

    # 自动订阅 ticker
    manager.subscribe(conn_id, ["ticker"], [initial_symbol])

    # 启动对应的 WS 代理
    proxy = manager._proxies.get(initial_exchange)
    if proxy:
        await proxy.start_if_needed("ticker", initial_symbol)

    try:
        # 发送欢迎消息
        await websocket.send_text(WSMessage(
            type="connected",
            data={"connection_id": conn_id, "subscribed": initial_symbol, "exchange": initial_exchange},
        ).model_dump_json())

        # 立即推送一次 REST ticker 数据，避免等待 WS 代理启动期间价格显示 $--
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                ticker_data = await _fetch_initial_ticker(client, initial_symbol, initial_exchange)
                if ticker_data:
                    await websocket.send_text(WSMessage(
                        type="ticker",
                        exchange=initial_exchange,
                        symbol=initial_symbol,
                        data=ticker_data,
                    ).model_dump_json())
        except Exception as exc:
            logger.debug("[WS] 初始 ticker 推送失败: %s", exc)

        while True:
            raw = await websocket.receive_text()
            try:
                cmd = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(WSMessage(
                    type="error",
                    data={"message": "无效的 JSON"},
                ).model_dump_json())
                continue

            action = cmd.get("action", "")

            if action == "ping":
                await websocket.send_text(WSMessage(type="pong", data={}).model_dump_json())

            elif action == "subscribe":
                channels = cmd.get("channels", ["ticker"])
                symbols = cmd.get("symbols", [])
                if not symbols:
                    symbols = [initial_symbol]
                exchange = cmd.get("exchange", initial_exchange)
                manager.subscribe(conn_id, channels, symbols)

                # 检查是否有 WS 代理可用，否则启用轮询降级
                proxy = manager._proxies.get(exchange)
                if proxy:
                    for ch in channels:
                        for sym in symbols:
                            await proxy.start_if_needed(ch, sym)

                await websocket.send_text(WSMessage(
                    type="subscribed",
                    data={"channels": channels, "symbols": symbols},
                ).model_dump_json())

            elif action == "unsubscribe":
                channels = cmd.get("channels", ["ticker"])
                symbols = cmd.get("symbols", [])
                manager.unsubscribe(conn_id, channels, symbols)

                # 检查代理是否可以停止
                for ex_name, proxy in manager._proxies.items():
                    for ch in channels:
                        for sym in symbols:
                            await proxy.stop_if_idle(ch, sym)

                await websocket.send_text(WSMessage(
                    type="unsubscribed",
                    data={"channels": channels, "symbols": symbols},
                ).model_dump_json())

            else:
                await websocket.send_text(WSMessage(
                    type="error",
                    data={"message": f"未知操作: {action}"},
                ).model_dump_json())

    except WebSocketDisconnect:
        logger.info("[WS] 连接断开: %s", conn_id)
    except Exception as exc:
        logger.error("[WS] 异常: %s: %s", conn_id, exc)
    finally:
        manager.unregister(conn_id)


# ==================== 初始 Ticker 推送辅助 ====================

async def _fetch_initial_ticker(
    client: httpx.AsyncClient, symbol: str, exchange: str
) -> dict | None:
    """通过 REST API 获取初始 ticker 数据，用于 WS 连接后立即推送"""
    try:
        if exchange == "binance":
            url = "https://api.binance.com/api/v3/ticker/24hr"
            params = {"symbol": symbol}
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            d = resp.json()
            return {
                "symbol": symbol,
                "price": d.get("lastPrice", "0"),
                "price_change": d.get("priceChange", "0"),
                "price_change_percent": d.get("priceChangePercent", "0"),
                "high_24h": d.get("highPrice", "0"),
                "low_24h": d.get("lowPrice", "0"),
                "volume_24h": d.get("volume", "0"),
            }
        elif exchange == "okx":
            # BTCUSDT → BTC-USDT
            inst_id = BinanceWSProxy.__bases__[0]._to_inst_id(None, symbol) if hasattr(BinanceWSProxy, '__bases__') else symbol
            # 简单转换
            for sc in ("USDT", "USDC", "BUSD"):
                if symbol.endswith(sc):
                    inst_id = f"{symbol[:-len(sc)]}-{sc}"
                    break
            url = "https://www.okx.com/api/v5/market/ticker"
            params = {"instId": inst_id}
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data", [])
            if not items:
                return None
            t = items[0]
            return {
                "symbol": symbol,
                "price": t.get("last", "0"),
                "price_change_percent": t.get("changeUtc24h", "0"),
                "high_24h": t.get("high24h", "0"),
                "low_24h": t.get("low24h", "0"),
                "volume_24h": t.get("vol24h", "0"),
            }
        elif exchange == "huobi":
            url = "https://api.huobi.pro/market/detail/merged"
            params = {"symbol": symbol.lower()}
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            tick = data.get("tick", {})
            close = tick.get("close", 0)
            open_price = tick.get("open", 0)
            change_pct = ((close - open_price) / open_price * 100) if open_price else 0
            return {
                "symbol": symbol,
                "price": str(close),
                "price_change_percent": str(change_pct),
                "high_24h": str(tick.get("high", 0)),
                "low_24h": str(tick.get("low", 0)),
                "volume_24h": str(tick.get("amount", 0)),
            }
    except Exception:
        return None


# ==================== 启动时初始化代理 ====================

async def init_ws_proxies() -> None:
    """应用启动时初始化 WS 代理（尝试加载 websockets 库）"""
    try:
        import websockets  # noqa: F401
        binance_proxy = BinanceWSProxy(manager)
        okx_proxy = OKXWSProxy(manager)
        huobi_proxy = HuobiWSProxy(manager)
        manager.register_proxy("binance", binance_proxy)
        manager.register_proxy("okx", okx_proxy)
        manager.register_proxy("huobi", huobi_proxy)
        logger.info("[WS] 代理初始化完成: binance, okx, huobi")
    except ImportError:
        logger.warning("[WS] websockets 库未安装，使用轮询降级模式")
        polling = PollingFallback(manager)
        await polling.start()


async def cleanup_ws_proxies() -> None:
    """应用关闭时清理"""
    for proxy in manager._proxies.values():
        for task in proxy._tasks.values():
            task.cancel()
    manager._subs.clear()
    logger.info("[WS] 代理已清理")
