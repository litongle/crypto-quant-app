"""
交易所适配器基类及统一模型
"""
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

import httpx

from app.core.exceptions import (
    ExchangeAPIError,
    NetworkError,
    OrderRejectedError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

# ==================== 重试配置 ====================

DEFAULT_RETRY_MAX_ATTEMPTS = 3      # 最大重试次数
DEFAULT_RETRY_BASE_DELAY = 1.0      # 基础延迟（秒）
DEFAULT_RETRY_MAX_DELAY = 30.0      # 最大延迟（秒）
DEFAULT_RETRY_BACKOFF_FACTOR = 2.0  # 退避因子


def _safe_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """安全转换 Decimal"""
    if value is None:
        return default
    try:
        s = str(value).strip()
        if not s:
            return default
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return default


def _safe_divide(
    numerator: Decimal, denominator: Decimal, default: Decimal | None = None
) -> Decimal | None:
    """安全除法"""
    if denominator == 0:
        return default
    try:
        return numerator / denominator
    except (InvalidOperation, ZeroDivisionError):
        return default


# ==================== 统一数据模型 ====================

@dataclass
class Ticker:
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
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    close_time: datetime


@dataclass
class OrderBook:
    bids: list[tuple[Decimal, Decimal]]
    asks: list[tuple[Decimal, Decimal]]


@dataclass
class Balance:
    asset: str
    free: Decimal
    locked: Decimal


@dataclass
class OrderResult:
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
    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    leverage: int


# ==================== 抽象基类 ====================

class BaseExchangeAdapter(ABC):
    """交易所适配器基类"""

    _shared_client: httpx.AsyncClient | None = None

    RETRY_MAX_ATTEMPTS: int = DEFAULT_RETRY_MAX_ATTEMPTS
    RETRY_BASE_DELAY: float = DEFAULT_RETRY_BASE_DELAY
    RETRY_MAX_DELAY: float = DEFAULT_RETRY_MAX_DELAY

    RATE_LIMIT_INTERVAL: float = 0.1
    _last_request_time: float = 0.0

    def __init__(self, api_key: str, secret_key: str, passphrase: str | None = None):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase

    @classmethod
    async def get_shared_client(cls) -> httpx.AsyncClient:
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(timeout=30.0)
        return cls._shared_client

    @staticmethod
    def _classify_error(exc: Exception, exchange: str) -> ExchangeAPIError:
        if isinstance(exc, ExchangeAPIError):
            return exc
        if isinstance(exc, httpx.TimeoutException):
            return NetworkError(exchange, f"请求超时: {exc}")
        if isinstance(exc, httpx.ConnectError):
            return NetworkError(exchange, f"连接失败: {exc}")
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code
            if status_code == 429:
                return RateLimitError(exchange, f"请求频率超限: {exc}")
            if status_code in (400, 401, 403):
                try:
                    body = exc.response.json()
                    detail_code = body.get("code") or body.get("err-code")
                    msg = body.get("msg") or body.get("err-msg") or str(exc)
                except Exception:
                    detail_code = None
                    msg = str(exc)
                return OrderRejectedError(exchange, msg, detail_code=detail_code)
            if status_code >= 500:
                return NetworkError(exchange, f"交易所服务异常: {exc}")
            return ExchangeAPIError(exchange, f"HTTP {status_code}: {exc}")
        return ExchangeAPIError(exchange, str(exc))

    async def _enforce_rate_limit(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.RATE_LIMIT_INTERVAL:
            await asyncio.sleep(self.RATE_LIMIT_INTERVAL - elapsed)
        self._last_request_time = time.monotonic()

    async def _request_with_retry(
        self,
        request_fn: Callable,
        *,
        max_attempts: int | None = None,
        base_delay: float | None = None,
        context: str = "",
    ) -> Any:
        attempts = max_attempts or self.RETRY_MAX_ATTEMPTS
        delay = base_delay or self.RETRY_BASE_DELAY
        last_exc: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                await self._enforce_rate_limit()
                result = await request_fn()
                return result
            except Exception as exc:
                classified = self._classify_error(exc, self.__class__.__name__)
                last_exc = classified
                if not classified.retryable or attempt >= attempts:
                    raise classified from exc
                actual_delay = min(
                    delay * (DEFAULT_RETRY_BACKOFF_FACTOR ** (attempt - 1)),
                    self.RETRY_MAX_DELAY,
                )
                await asyncio.sleep(actual_delay)
        raise last_exc or ExchangeAPIError(self.__class__.__name__, "未知错误")

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker: pass

    @abstractmethod
    async def get_klines(self, symbol: str, interval: str, limit: int = 100) -> list[Kline]: pass

    @abstractmethod
    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook: pass

    @abstractmethod
    async def get_balance(self) -> list[Balance]: pass

    @abstractmethod
    async def get_positions(self, symbol: str | None = None) -> list[PositionInfo]: pass

    @abstractmethod
    async def create_order(
        self, symbol: str, side: str, order_type: str, quantity: Decimal, price: Decimal | None = None,
    ) -> OrderResult: pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool: pass

    @abstractmethod
    async def get_order(self, order_id: str, symbol: str) -> OrderResult: pass

    async def create_stop_order(
        self, symbol: str, side: str, quantity: Decimal, stop_price: Decimal, order_type: str = "stop_loss",
    ) -> OrderResult:
        raise NotImplementedError(f"{self.__class__.__name__} 尚未实现条件单 API")
