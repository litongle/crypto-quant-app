"""
市场数据服务
"""
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


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

        # PRF-05: 尝试从 Redis 缓存获取
        cache_key = f"ticker:{exchange}:{symbol}"
        try:
            from app.redis import get_redis_pool
            import redis.asyncio as aioredis
            pool = await get_redis_pool()
            client = aioredis.Redis(connection_pool=pool)
            cached = await client.get(cache_key)
            await client.aclose()
            if cached:
                return json.loads(cached)
        except Exception:
            logger.debug("Redis cache miss for %s", cache_key)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if exchange == "binance":
                    url = f"https://api.binance.com/api/v3/ticker/24hr"
                    params = {"symbol": symbol}
                elif exchange == "okx":
                    url = f"https://www.okx.com/api/v5/market/ticker"
                    params = {"instId": f"{symbol[:-4]}-{symbol[-4:]}"}
                else:
                    raise AppException(
                        code="UNSUPPORTED_EXCHANGE",
                        message=f"不支持的交易所: {exchange}",
                    )

                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                # 统一格式化
                result = self._format_ticker(data, exchange, symbol)

                # 写入 Redis 缓存，TTL 10秒
                try:
                    from app.redis import get_redis_pool
                    import redis.asyncio as aioredis
                    pool = await get_redis_pool()
                    r = aioredis.Redis(connection_pool=pool)
                    await r.setex(cache_key, 10, json.dumps(result, default=str))
                    await r.aclose()
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
            async with httpx.AsyncClient(timeout=10.0) as client:
                if exchange == "binance":
                    url = f"https://api.binance.com/api/v3/klines"
                    params = {
                        "symbol": symbol,
                        "interval": interval,
                        "limit": limit,
                    }
                elif exchange == "okx":
                    url = f"https://www.okx.com/api/v5/market/candles"
                    params = {
                        "instId": f"{symbol[:-4]}-{symbol[-4:]}",
                        "bar": interval,
                        "limit": str(limit),
                    }
                else:
                    raise AppException(
                        code="UNSUPPORTED_EXCHANGE",
                        message=f"不支持的交易所: {exchange}",
                    )

                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

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
            async with httpx.AsyncClient(timeout=10.0) as client:
                if exchange == "binance":
                    url = f"https://api.binance.com/api/v3/depth"
                    params = {"symbol": symbol, "limit": limit}
                elif exchange == "okx":
                    url = f"https://www.okx.com/api/v5/market/books"
                    params = {"instId": f"{symbol[:-4]}-{symbol[-4:]}", "sz": str(limit)}
                else:
                    raise AppException(
                        code="UNSUPPORTED_EXCHANGE",
                        message=f"不支持的交易所: {exchange}",
                    )

                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

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
            ticker = data["data"][0]
            return {
                "symbol": symbol,
                "price": Decimal(ticker["last"]),
                "price_change": Decimal(ticker["last"]) - Decimal(ticker["open24h"]),
                "price_change_percent": (
                    (Decimal(ticker["last"]) - Decimal(ticker["open24h"]))
                    / Decimal(ticker["open24h"])
                    * 100
                ),
                "high_24h": Decimal(ticker["high24h"]),
                "low_24h": Decimal(ticker["low24h"]),
                "volume_24h": Decimal(ticker["vol24h"]),
                "quote_volume_24h": Decimal(ticker["volCcy24h"]),
                "timestamp": datetime.fromtimestamp(int(ticker["ts"]) / 1000),
            }

    def _format_klines(self, data: list, exchange: str) -> list[dict]:
        """格式化K线数据"""
        result = []
        for k in data:
            if exchange == "binance":
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
                result.append({
                    "timestamp": datetime.fromtimestamp(int(k[0]) / 1000),
                    "open": Decimal(k[1]),
                    "high": Decimal(k[2]),
                    "low": Decimal(k[3]),
                    "close": Decimal(k[4]),
                    "volume": Decimal(k[5]),
                    "close_time": datetime.fromtimestamp(int(k[6]) / 1000),
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
            books = data["data"][0]
            return {
                "bids": [
                    {"price": Decimal(p), "quantity": Decimal(q)}
                    for p, q, _, _ in books.get("bids", [])
                ],
                "asks": [
                    {"price": Decimal(p), "quantity": Decimal(q)}
                    for p, q, _, _ in books.get("asks", [])
                ],
            }
