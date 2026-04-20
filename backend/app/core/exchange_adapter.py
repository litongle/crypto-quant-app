"""
交易所适配器 - 统一接口
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx


@dataclass
class Ticker:
    """行情数据"""
    symbol: str
    price: Decimal
    price_change: Decimal
    price_change_percent: Decimal
    high_24h: Decimal
    low_24h: Decimal
    volume_24h: Decimal
    quote_volume_24h: Decimal
    timestamp: datetime


@dataclass
class Kline:
    """K线数据"""
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    close_time: datetime


@dataclass
class OrderBook:
    """订单簿"""
    bids: list[tuple[Decimal, Decimal]]  # [(price, quantity), ...]
    asks: list[tuple[Decimal, Decimal]]


@dataclass
class OrderBookEntry:
    """订单簿条目"""
    price: Decimal
    quantity: Decimal
    quote_quantity: Decimal


@dataclass
class Balance:
    """账户余额"""
    asset: str
    free: Decimal
    locked: Decimal


@dataclass
class OrderResult:
    """订单结果"""
    exchange_order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: Decimal
    price: Decimal | None
    status: str
    filled_quantity: Decimal
    avg_fill_price: Decimal | None


@dataclass
class PositionInfo:
    """持仓信息"""
    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    leverage: int


class BaseExchangeAdapter(ABC):
    """交易所适配器基类"""

    # 类级别共享 HTTP 客户端（PRF-01: 单例复用）
    _shared_client: httpx.AsyncClient | None = None

    def __init__(self, api_key: str, secret_key: str, passphrase: str | None = None):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase

    @classmethod
    async def get_shared_client(cls) -> httpx.AsyncClient:
        """获取共享的 httpx.AsyncClient 单例"""
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(timeout=30.0)
        return cls._shared_client

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """获取实时行情"""
        pass

    @abstractmethod
    async def get_klines(
        self, symbol: str, interval: str, limit: int = 100
    ) -> list[Kline]:
        """获取K线数据"""
        pass

    @abstractmethod
    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """获取订单簿"""
        pass

    @abstractmethod
    async def get_balance(self) -> list[Balance]:
        """获取账户余额"""
        pass

    @abstractmethod
    async def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        """获取持仓"""
        pass

    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
    ) -> OrderResult:
        """创建订单"""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        pass

    @abstractmethod
    async def get_order(self, order_id: str, symbol: str) -> OrderResult:
        """获取订单状态"""
        pass


class BinanceAdapter(BaseExchangeAdapter):
    """Binance 交易所适配器"""

    BASE_URL = "https://api.binance.com"

    async def get_ticker(self, symbol: str) -> Ticker:
        """获取实时行情"""
        client = await self.get_shared_client()
        resp = await client.get(
            f"{self.BASE_URL}/api/v3/ticker/24hr",
            params={"symbol": symbol}
        )
        data = resp.json()
        return Ticker(
            symbol=data["symbol"],
            price=Decimal(data["lastPrice"]),
            price_change=Decimal(data["priceChange"]),
            price_change_percent=Decimal(data["priceChangePercent"]),
            high_24h=Decimal(data["highPrice"]),
            low_24h=Decimal(data["lowPrice"]),
            volume_24h=Decimal(data["volume"]),
            quote_volume_24h=Decimal(data["quoteVolume"]),
            timestamp=datetime.fromtimestamp(data["closeTime"] / 1000),
        )

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 100
    ) -> list[Kline]:
        """获取K线数据"""
        client = await self.get_shared_client()
        resp = await client.get(
            f"{self.BASE_URL}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit}
        )
        klines = []
        for k in resp.json():
            klines.append(Kline(
                timestamp=datetime.fromtimestamp(k[0] / 1000),
                open=Decimal(k[1]),
                high=Decimal(k[2]),
                low=Decimal(k[3]),
                close=Decimal(k[4]),
                volume=Decimal(k[5]),
                close_time=datetime.fromtimestamp(k[6] / 1000),
            ))
        return klines

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """获取订单簿"""
        client = await self.get_shared_client()
        resp = await client.get(
            f"{self.BASE_URL}/api/v3/depth",
            params={"symbol": symbol, "limit": limit}
        )
        data = resp.json()
        return OrderBook(
            bids=[(Decimal(p), Decimal(q)) for p, q in data["bids"]],
            asks=[(Decimal(p), Decimal(q)) for p, q in data["asks"]],
        )

    async def get_balance(self) -> list[Balance]:
        """获取账户余额"""
        raise NotImplementedError()

    async def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        """获取持仓"""
        raise NotImplementedError()

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
    ) -> OrderResult:
        """创建订单"""
        raise NotImplementedError()

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        raise NotImplementedError()

    async def get_order(self, order_id: str, symbol: str) -> OrderResult:
        """获取订单状态"""
        raise NotImplementedError()


class OKXAdapter(BaseExchangeAdapter):
    """OKX 交易所适配器"""

    BASE_URL = "https://www.okx.com"

    def _to_inst_id(self, symbol: str) -> str:
        """转换 symbol 为 OKX instId 格式"""
        return f"{symbol[:-4]}-{symbol[-4:]}" if len(symbol) > 4 else symbol

    async def get_ticker(self, symbol: str) -> Ticker:
        """获取实时行情"""
        inst_id = self._to_inst_id(symbol)
        client = await self.get_shared_client()
        resp = await client.get(
            f"{self.BASE_URL}/api/v5/market/ticker",
            params={"instId": inst_id}
        )
        data = resp.json()["data"][0]
        return Ticker(
            symbol=symbol,
            price=Decimal(data["last"]),
            price_change=Decimal(data["last"]) - Decimal(data["open24h"]),
            price_change_percent=(
                (Decimal(data["last"]) - Decimal(data["open24h"]))
                / Decimal(data["open24h"]) * 100
                if Decimal(data["open24h"]) > 0 else Decimal("0")
            ),
            high_24h=Decimal(data["high24h"]),
            low_24h=Decimal(data["low24h"]),
            volume_24h=Decimal(data["vol24h"]),
            quote_volume_24h=Decimal(data["volCcy24h"]),
            timestamp=datetime.fromtimestamp(int(data["ts"]) / 1000),
        )

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 100
    ) -> list[Kline]:
        """获取K线数据"""
        inst_id = self._to_inst_id(symbol)
        client = await self.get_shared_client()
        resp = await client.get(
            f"{self.BASE_URL}/api/v5/market/candles",
            params={"instId": inst_id, "bar": interval, "limit": str(limit)}
        )
        klines = []
        for k in resp.json()["data"]:
            klines.append(Kline(
                timestamp=datetime.fromtimestamp(int(k[0]) / 1000),
                open=Decimal(k[1]),
                high=Decimal(k[2]),
                low=Decimal(k[3]),
                close=Decimal(k[4]),
                volume=Decimal(k[5]),
                close_time=datetime.fromtimestamp(int(k[6]) / 1000),
            ))
        return klines

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """获取订单簿"""
        inst_id = self._to_inst_id(symbol)
        client = await self.get_shared_client()
        resp = await client.get(
            f"{self.BASE_URL}/api/v5/market/books",
            params={"instId": inst_id, "sz": str(limit)}
        )
        data = resp.json()["data"][0]
        return OrderBook(
            bids=[(Decimal(p), Decimal(q)) for p, q, _, _ in data["bids"]],
            asks=[(Decimal(p), Decimal(q)) for p, q, _, _ in data["asks"]],
        )

    async def get_balance(self) -> list[Balance]:
        """获取账户余额"""
        raise NotImplementedError()

    async def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        """获取持仓"""
        raise NotImplementedError()

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
    ) -> OrderResult:
        """创建订单"""
        raise NotImplementedError()

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        raise NotImplementedError()

    async def get_order(self, order_id: str, symbol: str) -> OrderResult:
        """获取订单状态"""
        raise NotImplementedError()


def get_exchange_adapter(
    exchange: str,
    api_key: str,
    secret_key: str,
    passphrase: str | None = None,
) -> BaseExchangeAdapter:
    """获取交易所适配器工厂"""
    adapters = {
        "binance": BinanceAdapter,
        "okx": OKXAdapter,
        "huobi": None,  # TODO: 实现 Huobi 适配器
    }
    adapter_class = adapters.get(exchange.lower())
    if not adapter_class:
        raise ValueError(f"不支持的交易所: {exchange}")
    return adapter_class(api_key, secret_key, passphrase)
