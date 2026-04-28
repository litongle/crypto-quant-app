"""
WebSocket 交易所代理实现

支持 spot / perp 双市场:
  binance perp → wss://fstream.binance.com (USDT-M perpetual)
  okx     perp → 同 WS host,instId 改 BTC-USDT-SWAP
  huobi   perp → wss://api.hbdm.com/linear-swap-ws,topic 用 contract_code(BTC-USDT)

key 维度: (channel, symbol, market_type) — 同 symbol 的 spot 与 perp 是
两条独立的 WS 连接,价格不互串。
"""
import asyncio
import json
import logging
from typing import Any
import httpx
from app.core.trade_schemas import WSMessage

logger = logging.getLogger(__name__)


def _stream_key(channel: str, symbol: str, market_type: str) -> str:
    """统一的 task / 订阅 key"""
    return f"{channel}:{symbol}:{market_type}"


class ExchangeWSProxy:
    """交易所 WebSocket 代理基类"""
    EXCHANGE: str = ""

    def __init__(self, conn_manager: Any):
        self._manager = conn_manager
        self._tasks: dict[str, asyncio.Task] = {}

    async def start_if_needed(
        self, channel: str, symbol: str, market_type: str = "spot",
    ) -> None:
        key = _stream_key(channel, symbol, market_type)
        if key in self._tasks:
            return
        if self._manager.has_subscribers(channel, symbol):
            self._tasks[key] = asyncio.create_task(
                self._run_stream(channel, symbol, market_type),
                name=f"ws-proxy-{self.EXCHANGE}-{key}",
            )

    async def stop_if_idle(
        self, channel: str, symbol: str, market_type: str = "spot",
    ) -> None:
        key = _stream_key(channel, symbol, market_type)
        if not self._manager.has_subscribers(channel, symbol):
            task = self._tasks.pop(key, None)
            if task:
                task.cancel()

    async def _run_stream(
        self, channel: str, symbol: str, market_type: str,
    ) -> None:
        raise NotImplementedError

    async def _broadcast(self, msg: WSMessage) -> None:
        subscribers = self._manager.get_subscribers(msg.type, msg.symbol or "")
        for ws in subscribers:
            try:
                await ws.send_text(msg.model_dump_json())
            except Exception:
                pass

    async def _restart_on_error(
        self, channel: str, symbol: str, market_type: str,
    ) -> None:
        """连接异常后等待 5s 自动重连"""
        await asyncio.sleep(5)
        if self._manager.has_subscribers(channel, symbol):
            self._tasks.pop(_stream_key(channel, symbol, market_type), None)
            await self.start_if_needed(channel, symbol, market_type)


class BinanceWSProxy(ExchangeWSProxy):
    """Binance WebSocket 代理(spot: stream / perp: fstream)"""
    EXCHANGE = "binance"
    SPOT_BASE = "wss://stream.binance.com/ws"
    PERP_BASE = "wss://fstream.binance.com/ws"

    async def _run_stream(
        self, channel: str, symbol: str, market_type: str = "spot",
    ) -> None:
        symbol_lower = symbol.lower()
        stream = f"{symbol_lower}@ticker" if channel == "ticker" else \
                 f"{symbol_lower}@kline_1m" if channel == "kline" else \
                 f"{symbol_lower}@depth20@100ms"
        base = self.PERP_BASE if market_type == "perp" else self.SPOT_BASE
        url = f"{base}/{stream}"
        try:
            import websockets
            async with websockets.connect(url, ping_interval=20) as ws:
                async for raw in ws:
                    data = json.loads(raw)
                    msg = self._parse_message(data, channel, symbol)
                    if msg:
                        await self._broadcast(msg)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("[BinanceWS] 连接异常 %s/%s: %s", symbol, market_type, exc)
            await self._restart_on_error(channel, symbol, market_type)

    def _parse_message(self, data: dict, channel: str, symbol: str) -> WSMessage | None:
        if channel == "ticker" and "c" in data:
            return WSMessage(type="ticker", exchange="binance", symbol=symbol, data={
                "symbol": symbol, "price": data.get("c", "0"), "price_change": data.get("p", "0"),
                "price_change_percent": data.get("P", "0"), "high_24h": data.get("h", "0"),
                "low_24h": data.get("l", "0"), "volume_24h": data.get("v", "0"),
                "quote_volume_24h": data.get("q", "0"),
            })
        elif channel == "kline" and "k" in data:
            k = data["k"]
            return WSMessage(type="kline", exchange="binance", symbol=symbol, data={
                "symbol": symbol, "open": k.get("o", "0"), "high": k.get("h", "0"),
                "low": k.get("l", "0"), "close": k.get("c", "0"), "volume": k.get("v", "0"),
                "is_closed": k.get("x", False),
            })
        elif channel == "orderbook" and "b" in data:
            return WSMessage(type="orderbook", exchange="binance", symbol=symbol, data={
                "bids": [{"price": p, "quantity": q} for p, q in data.get("b", [])[:20]],
                "asks": [{"price": p, "quantity": q} for p, q in data.get("a", [])[:20]],
            })
        return None


class OKXProxy(ExchangeWSProxy):
    """OKX WebSocket 代理(spot 和 perp 同 host,只是 instId 不同)"""
    EXCHANGE = "okx"
    WS_URL = "wss://ws.okx.com:8443/ws/v5/public"

    async def _run_stream(
        self, channel: str, symbol: str, market_type: str = "spot",
    ) -> None:
        inst_id = self._to_inst_id(symbol, market_type)
        okx_ch = {"ticker": "tickers", "kline": "candle1m", "orderbook": "books5"}.get(channel)
        if not okx_ch:
            return
        sub_msg = json.dumps({"op": "subscribe", "args": [{"channel": okx_ch, "instId": inst_id}]})
        try:
            import websockets
            async with websockets.connect(self.WS_URL, ping_interval=20) as ws:
                await ws.send(sub_msg)
                async for raw in ws:
                    data = json.loads(raw)
                    if "data" in data:
                        msg = self._parse_message(data, channel, symbol)
                        if msg:
                            await self._broadcast(msg)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("[OKXWS] 连接异常 %s/%s: %s", symbol, market_type, exc)
            await self._restart_on_error(channel, symbol, market_type)

    @staticmethod
    def _to_inst_id(symbol: str, market_type: str = "spot") -> str:
        for sc in ("USDT", "USDC", "BUSD"):
            if symbol.endswith(sc):
                base = f"{symbol[:-len(sc)]}-{sc}"
                return f"{base}-SWAP" if market_type == "perp" else base
        return symbol

    def _parse_message(self, data: dict, channel: str, symbol: str) -> WSMessage | None:
        okx_ch = data.get("arg", {}).get("channel", "")
        items = data.get("data", [])
        if not items:
            return None
        if okx_ch == "tickers":
            t = items[0]
            return WSMessage(type="ticker", exchange="okx", symbol=symbol, data={
                "symbol": symbol, "price": t.get("last", "0"),
                "price_change_percent": t.get("changeUtc24h", "0"),
                "high_24h": t.get("high24h", "0"), "low_24h": t.get("low24h", "0"),
                "volume_24h": t.get("vol24h", "0"), "quote_volume_24h": t.get("volCcy24h", "0"),
            })
        elif okx_ch.startswith("candle"):
            k = items[0]
            return WSMessage(type="kline", exchange="okx", symbol=symbol, data={
                "symbol": symbol, "open": k[1], "high": k[2], "low": k[3],
                "close": k[4], "volume": k[5],
            })
        elif okx_ch == "books5":
            b = items[0]
            return WSMessage(type="orderbook", exchange="okx", symbol=symbol, data={
                "bids": [{"price": p, "quantity": q} for p, q, *_ in b.get("bids", [])[:20]],
                "asks": [{"price": p, "quantity": q} for p, q, *_ in b.get("asks", [])[:20]],
            })
        return None


class HuobiProxy(ExchangeWSProxy):
    """Huobi WebSocket 代理(spot: api.huobi.pro / perp: api.hbdm.com linear-swap-ws)"""
    EXCHANGE = "huobi"
    SPOT_WS = "wss://api.huobi.pro/ws"
    # Huobi 更名 HTX 后,旧 api.hbdm.com 域名在部分网络被墙;
    # 用新合约域 futures.htx.com 的 WS(/linear-swap-ws)
    PERP_WS = "wss://futures.htx.com/linear-swap-ws"

    async def _run_stream(
        self, channel: str, symbol: str, market_type: str = "spot",
    ) -> None:
        if market_type == "perp":
            # 火币线性永续 topic 用 contract_code(BTC-USDT)
            code = self._to_perp_code(symbol)
            topic = (
                f"market.{code}.detail" if channel == "ticker" else
                f"market.{code}.kline.1min" if channel == "kline" else
                f"market.{code}.depth.step0"
            )
            url = self.PERP_WS
        else:
            sym = symbol.lower()
            topic = (
                f"market.{sym}.detail" if channel == "ticker" else
                f"market.{sym}.kline.1min" if channel == "kline" else
                f"market.{sym}.depth.step0"
            )
            url = self.SPOT_WS

        sub_msg = json.dumps({"sub": topic, "id": f"sub-{symbol}-{market_type}"})
        try:
            import websockets
            import gzip
            async with websockets.connect(url, ping_interval=20) as ws:
                await ws.send(sub_msg)
                async for raw in ws:
                    decompressed = gzip.decompress(raw).decode("utf-8") if isinstance(raw, bytes) else raw
                    data = json.loads(decompressed)
                    if "ping" in data:
                        await ws.send(json.dumps({"pong": data["ping"]}))
                        continue
                    if "ch" in data:
                        msg = self._parse_message(data, channel, symbol)
                        if msg:
                            await self._broadcast(msg)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("[HuobiWS] 连接异常 %s/%s: %s", symbol, market_type, exc)
            await self._restart_on_error(channel, symbol, market_type)

    @staticmethod
    def _to_perp_code(symbol: str) -> str:
        """BTCUSDT → BTC-USDT(火币 USDT 本位永续 contract_code 格式)"""
        for sc in ("USDT", "USDC"):
            if symbol.endswith(sc):
                return f"{symbol[:-len(sc)]}-{sc}"
        return symbol

    def _parse_message(self, data: dict, channel: str, symbol: str) -> WSMessage | None:
        ch = data.get("ch", "")
        tick = data.get("tick", {})
        if not tick:
            return None
        if "detail" in ch or channel == "ticker":
            return WSMessage(type="ticker", exchange="huobi", symbol=symbol, data={
                "symbol": symbol, "price": str(tick.get("close", "0")),
                "price_change_percent": str(tick.get("change", "0")),
                "high_24h": str(tick.get("high", "0")), "low_24h": str(tick.get("low", "0")),
                "volume_24h": str(tick.get("vol", "0")),
                "quote_volume_24h": str(tick.get("amount", "0")),
            })
        elif "kline" in ch or channel == "kline":
            return WSMessage(type="kline", exchange="huobi", symbol=symbol, data={
                "symbol": symbol, "open": str(tick.get("open", "0")),
                "high": str(tick.get("high", "0")), "low": str(tick.get("low", "0")),
                "close": str(tick.get("close", "0")), "volume": str(tick.get("vol", "0")),
            })
        elif "depth" in ch or channel == "orderbook":
            return WSMessage(type="orderbook", exchange="huobi", symbol=symbol, data={
                "bids": [{"price": p, "quantity": q} for p, q in tick.get("bids", [])[:20]],
                "asks": [{"price": p, "quantity": q} for p, q in tick.get("asks", [])[:20]],
            })
        return None


class PollingFallback:
    """轮询降级模式(websockets 库不可用时启用,只支持现货)"""
    def __init__(self, conn_manager: Any):
        self._manager = conn_manager
        self._tasks: dict[str, asyncio.Task] = {}
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tasks["polling"] = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks.values():
            task.cancel()

    async def _poll_loop(self) -> None:
        from app.core.exchanges.binance import BinanceAdapter
        from app.core.trade_schemas import TickerSchema
        adapter = BinanceAdapter("", "")
        while self._running:
            try:
                symbols = set()
                for sub in self._manager._subs.values():
                    symbols.update(sub.symbols)
                if not symbols:
                    await asyncio.sleep(2)
                    continue
                for sym in list(symbols)[:10]:
                    try:
                        ticker = await adapter.get_ticker(sym)
                        msg = WSMessage(
                            type="ticker", exchange="binance", symbol=sym,
                            data=TickerSchema.from_dataclass(ticker).model_dump(),
                        )
                        await self._broadcast(msg)
                    except Exception:
                        pass
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(5)

    async def _broadcast(self, msg: WSMessage) -> None:
        subscribers = self._manager.get_subscribers(msg.type, msg.symbol or "")
        for ws in subscribers:
            try:
                await ws.send_text(msg.model_dump_json())
            except Exception:
                pass
