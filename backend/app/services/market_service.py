"""
市场数据服务
"""
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)

# P1-3: 模块级 httpx.AsyncClient 单例，复用连接池
_http_client: httpx.AsyncClient | None = None

# P1-4: 模块级 Redis 客户端单例，复用连接
_redis_client = None


async def get_http_client() -> httpx.AsyncClient:
    """获取全局 httpx.AsyncClient 单例（懒加载）"""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client


async def get_redis_client():
    """P1-4: 获取全局 Redis 客户端单例（懒加载，复用连接池）"""
    global _redis_client
    if _redis_client is None:
        try:
            from app.redis import get_redis_pool
            import redis.asyncio as aioredis
            pool = await get_redis_pool()
            _redis_client = aioredis.Redis(connection_pool=pool)
        except Exception:
            return None
    return _redis_client


async def close_market_resources():
    """关闭市场服务的全局资源（应用关闭时调用）"""
    global _http_client, _redis_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None
    if _redis_client:
        try:
            await _redis_client.aclose()
        except Exception:
            pass
        _redis_client = None


# 支持的交易对
SUPPORTED_SYMBOLS = {
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT",
    "ADAUSDT", "XRPUSDT", "DOTUSDT", "MATICUSDT", "LINKUSDT",
}

# K线周期
KLINE_INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]


class MarketService:
    """市场数据服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_ticker(self, symbol: str, exchange: str = "binance") -> dict:
        """
        获取实时行情（带 Redis 缓存，PRF-05）
        
        Args:
            symbol: 交易对，如 BTCUSDT
            exchange: 交易所
        
        Returns:
            dict: 行情数据
        """
        symbol = symbol.upper()
        if symbol not in SUPPORTED_SYMBOLS:
            raise AppException(
                code="INVALID_SYMBOL",
                message=f"不支持的交易对: {symbol}",
            )

        # PRF-05: 尝试从 Redis 缓存获取（P1-4: 复用 Redis 客户端）
        cache_key = f"ticker:{exchange}:{symbol}"
        try:
            r = await get_redis_client()
            if r:
                cached = await r.get(cache_key)
                if cached:
                    return json.loads(cached)
        except Exception:
            logger.debug("Redis cache miss for %s", cache_key)

        try:
            client = await get_http_client()
            if exchange == "binance":
                url = "https://api.binance.com/api/v3/ticker/24hr"
                params = {"symbol": symbol}
            elif exchange == "okx":
                url = "https://www.okx.com/api/v5/market/ticker"
                params = {"instId": self._to_okx_inst_id(symbol)}
            elif exchange == "huobi":
                url = "https://api.huobi.pro/market/detail/merged"
                params = {"symbol": symbol.lower()}
            else:
                raise AppException(
                    code="UNSUPPORTED_EXCHANGE",
                    message=f"不支持的交易所: {exchange}",
                )

            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # OKX / Huobi: 检查 API 层错误码
            self._check_api_error(data, exchange)

            # 统一格式化
            result = self._format_ticker(data, exchange, symbol)

            # 写入 Redis 缓存，TTL 10秒（P1-4: 复用 Redis 客户端）
            try:
                r = await get_redis_client()
                if r:
                    await r.setex(cache_key, 10, json.dumps(result, default=str))
            except Exception:
                logger.debug("Redis cache write failed for %s", cache_key)

            return result

        except httpx.HTTPError as e:
            raise AppException(
                code="EXTERNAL_API_ERROR",
                message=f"获取行情失败: {str(e)}",
            )

    async def get_kline(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
        exchange: str = "binance",
    ) -> list[dict]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对
            interval: K线周期 (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)
            limit: 数据条数 (1-1000)
            exchange: 交易所
        
        Returns:
            list[dict]: K线数据列表
        """
        symbol = symbol.upper()
        if symbol not in SUPPORTED_SYMBOLS:
            raise AppException(
                code="INVALID_SYMBOL",
                message=f"不支持的交易对: {symbol}",
            )
        if interval not in KLINE_INTERVALS:
            raise AppException(
                code="INVALID_INTERVAL",
                message=f"不支持的周期: {interval}",
            )
        if limit < 1 or limit > 1000:
            raise AppException(
                code="INVALID_LIMIT",
                message="limit必须在1-1000之间",
            )

        try:
            client = await get_http_client()
            if exchange == "binance":
                url = "https://api.binance.com/api/v3/klines"
                params = {
                    "symbol": symbol,
                    "interval": interval,
                    "limit": limit,
                }
            elif exchange == "okx":
                url = "https://www.okx.com/api/v5/market/candles"
                params = {
                    "instId": self._to_okx_inst_id(symbol),
                    "bar": self._to_okx_bar(interval),
                    "limit": str(limit),
                }
            elif exchange == "huobi":
                url = "https://api.huobi.pro/market/history/kline"
                params = {
                    "symbol": symbol.lower(),
                    "period": self._to_huobi_period(interval),
                    "size": limit,
                }
            else:
                raise AppException(
                    code="UNSUPPORTED_EXCHANGE",
                    message=f"不支持的交易所: {exchange}",
                )

            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # OKX / Huobi: 检查 API 层错误码
            self._check_api_error(data, exchange)

            return self._format_klines(data, exchange)

        except httpx.HTTPError as e:
            raise AppException(
                code="EXTERNAL_API_ERROR",
                message=f"获取K线失败: {str(e)}",
            )

    async def get_orderbook(
        self, symbol: str, limit: int = 20, exchange: str = "binance"
    ) -> dict:
        """获取订单簿"""
        symbol = symbol.upper()

        try:
            client = await get_http_client()
            if exchange == "binance":
                url = "https://api.binance.com/api/v3/depth"
                params = {"symbol": symbol, "limit": limit}
            elif exchange == "okx":
                url = "https://www.okx.com/api/v5/market/books"
                params = {"instId": self._to_okx_inst_id(symbol), "sz": str(limit)}
            elif exchange == "huobi":
                url = "https://api.huobi.pro/market/depth"
                params = {"symbol": symbol.lower(), "type": "step0", "depth": limit}
            else:
                raise AppException(
                    code="UNSUPPORTED_EXCHANGE",
                    message=f"不支持的交易所: {exchange}",
                )

            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            self._check_api_error(data, exchange)

            return self._format_orderbook(data, exchange)

        except httpx.HTTPError as e:
            raise AppException(
                code="EXTERNAL_API_ERROR",
                message=f"获取订单簿失败: {str(e)}",
            )

    def _format_ticker(
        self, data: dict, exchange: str, symbol: str
    ) -> dict:
        """格式化行情数据"""
        if exchange == "binance":
            return {
                "symbol": data["symbol"],
                "price": Decimal(data["lastPrice"]),
                "price_change": Decimal(data["priceChange"]),
                "price_change_percent": Decimal(data["priceChangePercent"]),
                "high_24h": Decimal(data["highPrice"]),
                "low_24h": Decimal(data["lowPrice"]),
                "volume_24h": Decimal(data["volume"]),
                "quote_volume_24h": Decimal(data["quoteVolume"]),
                "timestamp": datetime.fromtimestamp(data["closeTime"] / 1000),
            }
        elif exchange == "okx":
            items = data.get("data", [])
            if not items:
                raise AppException(code="EXTERNAL_API_ERROR", message=f"OKX 未返回 {symbol} 行情数据")
            ticker = items[0]
            last = Decimal(ticker["last"])
            open24h = Decimal(ticker["open24h"])
            return {
                "symbol": symbol,
                "price": last,
                "price_change": last - open24h,
                "price_change_percent": (
                    (last - open24h) / open24h * 100 if open24h else Decimal("0")
                ),
                "high_24h": Decimal(ticker["high24h"]),
                "low_24h": Decimal(ticker["low24h"]),
                "volume_24h": Decimal(ticker["vol24h"]),
                "quote_volume_24h": Decimal(ticker["volCcy24h"]),
                "timestamp": datetime.fromtimestamp(int(ticker["ts"]) / 1000),
            }
        elif exchange == "huobi":
            tick = data.get("tick", {})
            close = Decimal(str(tick.get("close", 0)))
            open_price = Decimal(str(tick.get("open", 0)))
            # 火币: ts 在顶层, vol=成交额(USDT), amount=成交量(币)
            ts_ms = data.get("ts", tick.get("version", 0))
            return {
                "symbol": symbol,
                "price": close,
                "price_change": close - open_price,
                "price_change_percent": (
                    (close - open_price) / open_price * 100 if open_price else Decimal("0")
                ),
                "high_24h": Decimal(str(tick.get("high", 0))),
                "low_24h": Decimal(str(tick.get("low", 0))),
                "volume_24h": Decimal(str(tick.get("amount", 0))),
                "quote_volume_24h": Decimal(str(tick.get("vol", 0))),
                "timestamp": datetime.fromtimestamp(ts_ms / 1000) if ts_ms else datetime.now(),
            }

    def _format_klines(self, data: Any, exchange: str) -> list[dict]:
        """格式化K线数据"""
        result = []
        if exchange == "binance":
            for k in data:
                result.append({
                    "timestamp": datetime.fromtimestamp(k[0] / 1000),
                    "open": Decimal(k[1]),
                    "high": Decimal(k[2]),
                    "low": Decimal(k[3]),
                    "close": Decimal(k[4]),
                    "volume": Decimal(k[5]),
                    "close_time": datetime.fromtimestamp(k[6] / 1000),
                })
        elif exchange == "okx":
            # OKX K线数据是倒序（最新在前），需反转为时间正序
            candles = data.get("data", []) if isinstance(data, dict) else data
            for k in reversed(candles):
                result.append({
                    "timestamp": datetime.fromtimestamp(int(k[0]) / 1000),
                    "open": Decimal(str(k[1])),
                    "high": Decimal(str(k[2])),
                    "low": Decimal(str(k[3])),
                    "close": Decimal(str(k[4])),
                    "volume": Decimal(str(k[5])),
                    "close_time": datetime.fromtimestamp(int(k[0]) / 1000),
                })
        elif exchange == "huobi":
            items = data.get("data", []) if isinstance(data, dict) else data
            # 火币K线已是时间正序; id=时间戳秒, vol=成交额, amount=成交量
            for k in items:
                result.append({
                    "timestamp": datetime.fromtimestamp(k["id"]),
                    "open": Decimal(str(k["open"])),
                    "high": Decimal(str(k["high"])),
                    "low": Decimal(str(k["low"])),
                    "close": Decimal(str(k["close"])),
                    "volume": Decimal(str(k.get("amount", k.get("vol", 0)))),
                    "close_time": datetime.fromtimestamp(k["id"]),
                })
        return result

    def _format_orderbook(self, data: dict, exchange: str) -> dict:
        """格式化订单簿数据"""
        if exchange == "binance":
            return {
                "bids": [
                    {"price": Decimal(p), "quantity": Decimal(q)}
                    for p, q in data.get("bids", [])
                ],
                "asks": [
                    {"price": Decimal(p), "quantity": Decimal(q)}
                    for p, q in data.get("asks", [])
                ],
            }
        elif exchange == "okx":
            items = data.get("data", [])
            if not items:
                return {"bids": [], "asks": []}
            books = items[0]
            return {
                "bids": [
                    {"price": Decimal(str(p)), "quantity": Decimal(str(q))}
                    for p, q, *_ in books.get("bids", [])
                ],
                "asks": [
                    {"price": Decimal(str(p)), "quantity": Decimal(str(q))}
                    for p, q, *_ in books.get("asks", [])
                ],
            }
        elif exchange == "huobi":
            tick = data.get("tick", {})
            return {
                "bids": [
                    {"price": Decimal(str(p)), "quantity": Decimal(str(q))}
                    for p, q in tick.get("bids", [])
                ],
                "asks": [
                    {"price": Decimal(str(p)), "quantity": Decimal(str(q))}
                    for p, q in tick.get("asks", [])
                ],
            }

    # ==================== 交易所辅助方法 ====================

    @staticmethod
    def _to_okx_inst_id(symbol: str) -> str:
        """BTCUSDT → BTC-USDT (OKX instId 格式)"""
        stablecoins = ("USDT", "USDC", "BUSD")
        for sc in stablecoins:
            if symbol.endswith(sc):
                base = symbol[:-len(sc)]
                return f"{base}-{sc}"
        return symbol

    @staticmethod
    def _to_okx_bar(interval: str) -> str:
        """OKX K线周期映射: 1h→1H, 4h→4H, 1d→1D, 1w→1W, 其他保持"""
        mapping = {
            "1h": "1H", "4h": "4H", "1d": "1D", "1w": "1W",
        }
        return mapping.get(interval, interval)

    @staticmethod
    def _to_huobi_period(interval: str) -> str:
        """K线周期映射: 1m→1min, 1h→60min, 1d→1day, ..."""
        mapping = {
            "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
            "1h": "60min", "4h": "4hour", "1d": "1day", "1w": "1week",
        }
        return mapping.get(interval, "60min")

    @staticmethod
    def _check_api_error(data: dict, exchange: str) -> None:
        """检查交易所 API 层面的错误码（HTTP 200 但业务报错）"""
        if exchange == "okx":
            code = str(data.get("code", "0"))
            if code != "0":
                msg = data.get("msg", "未知错误")
                raise AppException(
                    code="EXTERNAL_API_ERROR",
                    message=f"OKX API 错误 ({code}): {msg}",
                )
        elif exchange == "huobi":
            status = data.get("status", "")
            if status == "error":
                err_code = data.get("err-code", "unknown")
                err_msg = data.get("err-msg", "未知错误")
                raise AppException(
                    code="EXTERNAL_API_ERROR",
                    message=f"火币 API 错误 ({err_code}): {err_msg}",
                )
