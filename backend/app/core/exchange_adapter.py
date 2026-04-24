"""
交易所适配器 - 统一接口 + 三大交易所实现

架构：
- 全异步 httpx.AsyncClient 单例复用（PRF-01）
- HMAC SHA256 签名认证
- 统一数据模型（Ticker/Kline/OrderBook/Balance/OrderResult/PositionInfo）
- 指数退避重试 + 限流控制（REL-01）
- 安全 Decimal 转换，防 DivisionByZero（SAFE-01）
- 支持交易所：Binance / OKX / Huobi
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
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

# 默认重试配置
DEFAULT_RETRY_MAX_ATTEMPTS = 3      # 最大重试次数
DEFAULT_RETRY_BASE_DELAY = 1.0      # 基础延迟（秒）
DEFAULT_RETRY_MAX_DELAY = 30.0      # 最大延迟（秒）
DEFAULT_RETRY_BACKOFF_FACTOR = 2.0  # 退避因子


def _safe_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """安全转换 Decimal，防止 ValueError / DivisionByZero

    - None / "" → default
    - "0.0" / "0" → Decimal("0")
    - float 精度问题 → 先转 str 再转 Decimal
    """
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
    """安全除法，防止 DivisionByZero

    分母为 0 时返回 default（None 表示无法计算）
    """
    if denominator == 0:
        return default
    try:
        return numerator / denominator
    except (InvalidOperation, ZeroDivisionError):
        return default


# ==================== 统一数据模型 ====================

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


# ==================== 订单状态映射 ====================

# Binance: NEW PARTIALLY_FILLED FILLED CANCELED EXPIRED REJECTED
_BINANCE_STATUS_MAP = {
    "NEW": "pending",
    "PARTIALLY_FILLED": "partial",
    "FILLED": "filled",
    "CANCELED": "cancelled",
    "EXPIRED": "cancelled",
    "REJECTED": "rejected",
    "PENDING_CANCEL": "pending",
}

# OKX: canceled live partially_filled filled
_OKX_STATUS_MAP = {
    "live": "pending",
    "partially_filled": "partial",
    "filled": "filled",
    "canceled": "cancelled",
}

# Huobi: submitted partial-filled filled canceled
_HUOBI_STATUS_MAP = {
    "submitted": "pending",
    "partial-filled": "partial",
    "filled": "filled",
    "canceled": "cancelled",
    "partial-canceled": "cancelled",
}


# ==================== 抽象基类 ====================

class BaseExchangeAdapter(ABC):
    """交易所适配器基类

    提供所有子类共享的基础设施：
    - HTTP 客户端单例复用
    - 请求重试 + 指数退避
    - 限流控制
    - 异常分类
    """

    # 类级别共享 HTTP 客户端（PRF-01: 单例复用）
    _shared_client: httpx.AsyncClient | None = None

    # 子类可覆盖的重试参数
    RETRY_MAX_ATTEMPTS: int = DEFAULT_RETRY_MAX_ATTEMPTS
    RETRY_BASE_DELAY: float = DEFAULT_RETRY_BASE_DELAY
    RETRY_MAX_DELAY: float = DEFAULT_RETRY_MAX_DELAY

    # 限流：最小请求间隔（秒），子类可覆盖
    RATE_LIMIT_INTERVAL: float = 0.1  # 100ms
    _last_request_time: float = 0.0

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

    @staticmethod
    def _classify_error(exc: Exception, exchange: str) -> ExchangeAPIError:
        """将原始异常分类为具体的 ExchangeAPIError 子类

        分类逻辑：
        - httpx.TimeoutException → NetworkError（可重试）
        - httpx.ConnectError → NetworkError（可重试）
        - HTTP 429 → RateLimitError（可重试）
        - HTTP 400/401/403 → OrderRejectedError（不可重试）
        - ExchangeAPIError → 原样返回
        - 其他 → ExchangeAPIError（不可重试）
        """
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
        """限流控制：确保两次请求之间有最小间隔"""
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
        """带指数退避重试的请求执行器

        Args:
            request_fn: 异步请求函数（无参数）
            max_attempts: 最大尝试次数（默认用类属性）
            base_delay: 基础延迟秒数（默认用类属性）
            context: 请求上下文描述，用于日志

        Returns:
            request_fn 的返回值

        Raises:
            ExchangeAPIError: 重试耗尽后抛出最后一次异常
        """
        attempts = max_attempts or self.RETRY_MAX_ATTEMPTS
        delay = base_delay or self.RETRY_BASE_DELAY
        last_exc: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                await self._enforce_rate_limit()
                result = await request_fn()
                if attempt > 1:
                    logger.info(
                        "[%s] 请求成功（第 %d 次尝试）%s",
                        self.__class__.__name__, attempt,
                        f" context={context}" if context else "",
                    )
                return result
            except Exception as exc:
                classified = self._classify_error(exc, self.__class__.__name__)
                last_exc = classified

                if not classified.retryable or attempt >= attempts:
                    logger.error(
                        "[%s] 请求失败（第 %d/%d 次）%s: %s [%s]",
                        self.__class__.__name__, attempt, attempts,
                        f" context={context}" if context else "",
                        classified.message, classified.code,
                    )
                    raise classified from exc

                # 可重试：指数退避
                actual_delay = min(
                    delay * (DEFAULT_RETRY_BACKOFF_FACTOR ** (attempt - 1)),
                    self.RETRY_MAX_DELAY,
                )
                logger.warning(
                    "[%s] 请求失败（第 %d/%d 次），%.1fs 后重试 %s: %s [%s]",
                    self.__class__.__name__, attempt, attempts,
                    actual_delay,
                    f" context={context}" if context else "",
                    classified.message, classified.code,
                )
                await asyncio.sleep(actual_delay)

        # 理论上不会到这里，但保险起见
        raise last_exc or ExchangeAPIError(self.__class__.__name__, "未知错误")

    # ---- 行情接口 ----

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

    # ---- 交易接口 ----

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


# ==================== Binance 适配器 ====================

class BinanceAdapter(BaseExchangeAdapter):
    """Binance 交易所适配器

    API 文档: https://binance-docs.github.io/apidocs/
    签名: HMAC SHA256，参数加 timestamp + signature
    Header: X-MBX-APIKEY
    """

    BASE_URL = "https://api.binance.com"
    TESTNET_URL = "https://testnet.binance.vision"

    # Binance 限流：10 requests/second (order)，1200 requests/min (general)
    RATE_LIMIT_INTERVAL = 0.1

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str | None = None,
        testnet: bool = False,
    ):
        super().__init__(api_key, secret_key, passphrase)
        self.base_url = self.TESTNET_URL if testnet else self.BASE_URL
        self.testnet = testnet

    def _sign_params(self, params: dict) -> dict:
        """Binance HMAC SHA256 签名

        规则：params + timestamp → urlencode → HMAC SHA256 → signature
        """
        params["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(params)
        signature = hmac.new(
            self.secret_key.encode(), query_string.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _auth_headers(self) -> dict[str, str]:
        """Binance API Key Header"""
        return {"X-MBX-APIKEY": self.api_key}

    def _check_response(self, data: dict, exchange: str = "Binance") -> None:
        """检查交易所返回是否含错误"""
        if "code" in data and data["code"] != 200:
            msg = data.get("msg", "Unknown error")
            code = str(data.get("code", ""))
            # Binance 常见拒单错误码
            reject_codes = {
                "-2010",  # NEW_ORDER_REJECTED
                "-1013",  # INVALID_QUANTITY
                "-2015",  # INVALID_API_KEY
            }
            if code in reject_codes:
                raise OrderRejectedError(exchange, f"[{code}] {msg}", detail_code=code)
            raise ExchangeAPIError(exchange=exchange, message=f"[{code}] {msg}", detail_code=code)

    # ---- 行情接口 ----

    async def get_ticker(self, symbol: str) -> Ticker:
        async def _do():
            client = await self.get_shared_client()
            resp = await client.get(
                f"{self.base_url}/api/v3/ticker/24hr",
                params={"symbol": symbol},
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_ticker({symbol})")
        return Ticker(
            symbol=data["symbol"],
            price=_safe_decimal(data.get("lastPrice")),
            price_change=_safe_decimal(data.get("priceChange")),
            price_change_percent=_safe_decimal(data.get("priceChangePercent")),
            high_24h=_safe_decimal(data.get("highPrice")),
            low_24h=_safe_decimal(data.get("lowPrice")),
            volume_24h=_safe_decimal(data.get("volume")),
            quote_volume_24h=_safe_decimal(data.get("quoteVolume")),
            timestamp=datetime.fromtimestamp(
                _safe_decimal(data.get("closeTime"), Decimal("0")) / 1000,
                tz=timezone.utc,
            ),
        )

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 100
    ) -> list[Kline]:
        async def _do():
            client = await self.get_shared_client()
            resp = await client.get(
                f"{self.base_url}/api/v3/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit},
            )
            resp.raise_for_status()
            return resp.json()

        raw = await self._request_with_retry(_do, context=f"get_klines({symbol})")
        klines = []
        for k in raw:
            klines.append(Kline(
                timestamp=datetime.fromtimestamp(_safe_decimal(k[0]) / 1000, tz=timezone.utc),
                open=_safe_decimal(k[1]),
                high=_safe_decimal(k[2]),
                low=_safe_decimal(k[3]),
                close=_safe_decimal(k[4]),
                volume=_safe_decimal(k[5]),
                close_time=datetime.fromtimestamp(_safe_decimal(k[6]) / 1000, tz=timezone.utc),
            ))
        return klines

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        async def _do():
            client = await self.get_shared_client()
            resp = await client.get(
                f"{self.base_url}/api/v3/depth",
                params={"symbol": symbol, "limit": limit},
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_orderbook({symbol})")
        return OrderBook(
            bids=[(_safe_decimal(p), _safe_decimal(q)) for p, q in data.get("bids", [])],
            asks=[(_safe_decimal(p), _safe_decimal(q)) for p, q in data.get("asks", [])],
        )

    # ---- 交易接口 ----

    async def get_balance(self) -> list[Balance]:
        """获取现货账户余额（过滤零余额）"""
        async def _do():
            client = await self.get_shared_client()
            params = self._sign_params({})
            resp = await client.get(
                f"{self.base_url}/api/v3/account",
                params=params,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context="get_balance")
        self._check_response(data)
        balances = []
        for b in data.get("balances", []):
            free = _safe_decimal(b.get("free"))
            locked = _safe_decimal(b.get("locked"))
            if free > 0 or locked > 0:
                balances.append(Balance(
                    asset=b.get("asset", ""),
                    free=free,
                    locked=locked,
                ))
        return balances

    async def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        """现货无持仓概念，返回空列表"""
        return []

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
    ) -> OrderResult:
        """创建现货订单

        Binance Spot: POST /api/v3/order
        - MARKET: 只需 symbol + side + type + quantity
        - LIMIT: 还需 price + timeInForce
        """
        async def _do():
            client = await self.get_shared_client()
            params: dict[str, Any] = {
                "symbol": symbol.upper(),
                "side": side.upper(),
                "type": order_type.upper(),
                "quantity": f"{quantity:.8f}".rstrip("0").rstrip("."),
            }
            if order_type.lower() == "limit":
                if price is None:
                    raise OrderRejectedError("Binance", "限价单必须指定价格")
                params["price"] = f"{price:.8f}".rstrip("0").rstrip(".")
                params["timeInForce"] = "GTC"

            params = self._sign_params(params)
            resp = await client.post(
                f"{self.base_url}/api/v3/order",
                params=params,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(
            _do, max_attempts=1,  # 下单不重试（幂等性无保证）
            context=f"create_order({symbol},{side},{order_type})",
        )
        self._check_response(data)

        executed_qty = _safe_decimal(data.get("executedQty"))
        cumm_quote = _safe_decimal(data.get("cummulativeQuoteQty"))

        return OrderResult(
            exchange_order_id=str(data.get("orderId", "")),
            symbol=data.get("symbol", symbol),
            side=data.get("side", side).lower(),
            order_type=data.get("type", order_type).lower(),
            quantity=_safe_decimal(data.get("origQty"), quantity),
            price=_safe_decimal(data.get("price")) if _safe_decimal(data.get("price")) > 0 else None,
            status=_BINANCE_STATUS_MAP.get(data.get("status", ""), "pending"),
            filled_quantity=executed_qty,
            avg_fill_price=_safe_divide(cumm_quote, executed_qty),
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        async def _do():
            client = await self.get_shared_client()
            params = self._sign_params({
                "symbol": symbol.upper(),
                "orderId": order_id,
            })
            resp = await client.delete(
                f"{self.base_url}/api/v3/order",
                params=params,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(
            _do, max_attempts=2,  # 撤单可重试一次
            context=f"cancel_order({symbol},{order_id})",
        )
        self._check_response(data)
        return data.get("status") in ("CANCELED", "CANCELLED")

    async def get_order(self, order_id: str, symbol: str) -> OrderResult:
        """查询订单状态"""
        async def _do():
            client = await self.get_shared_client()
            params = self._sign_params({
                "symbol": symbol.upper(),
                "orderId": order_id,
            })
            resp = await client.get(
                f"{self.base_url}/api/v3/order",
                params=params,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_order({symbol},{order_id})")
        self._check_response(data)

        executed_qty = _safe_decimal(data.get("executedQty"))
        cumm_quote = _safe_decimal(data.get("cummulativeQuoteQty"))

        return OrderResult(
            exchange_order_id=str(data.get("orderId", "")),
            symbol=data.get("symbol", symbol),
            side=data.get("side", side if "side" in data else "buy").lower(),
            order_type=data.get("type", order_type if "type" in data else "market").lower(),
            quantity=_safe_decimal(data.get("origQty")),
            price=_safe_decimal(data.get("price")) if _safe_decimal(data.get("price")) > 0 else None,
            status=_BINANCE_STATUS_MAP.get(data.get("status", ""), "pending"),
            filled_quantity=executed_qty,
            avg_fill_price=_safe_divide(cumm_quote, executed_qty),
        )


# ==================== OKX 适配器 ====================

class OKXAdapter(BaseExchangeAdapter):
    """OKX 交易所适配器

    API 文档: https://www.okx.com/docs-v5/en/
    签名: HMAC SHA256，timestamp + method + requestPath + body → Base64
    Headers: OK-ACCESS-KEY / OK-ACCESS-SIGN / OK-ACCESS-TIMESTAMP / OK-ACCESS-PASSPHRASE
    """

    BASE_URL = "https://www.okx.com"
    DEMO_URL = "https://www.okx.com"  # OKX 用 flag 区分模拟盘

    # OKX 限流：20 requests/2s (trade)
    RATE_LIMIT_INTERVAL = 0.1

    # 服务器时间偏移（毫秒），首次请求前同步
    _time_offset_ms: int = 0
    _time_synced: bool = False

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str | None = None,
        is_demo: bool = False,
    ):
        super().__init__(api_key, secret_key, passphrase)
        self.is_demo = is_demo
        # OKX 要求 passphrase 必须与创建 API Key 时一致
        if not self.passphrase:
            logger.warning(
                "[OKXAdapter] passphrase 为空！OKX 认证将失败（错误码 50113）。"
                "请在添加账户时填写创建 API Key 时设置的 Passphrase。"
            )

    def _to_inst_id(self, symbol: str) -> str:
        """转换 symbol 为 OKX instId 格式

        BTCUSDT → BTC-USDT
        ETHUSDT → ETH-USDT
        """
        # 常见 USDT 对
        stablecoins = ("USDT", "USDC", "BUSD")
        for sc in stablecoins:
            if symbol.endswith(sc):
                base = symbol[: -len(sc)]
                return f"{base}-{sc}"
        return symbol

    def _okx_timestamp(self) -> str:
        """OKX 要求的 ISO 8601 时间戳（毫秒级，已校准服务器偏移）"""
        from datetime import timedelta
        adjusted = datetime.now(timezone.utc) + timedelta(milliseconds=self._time_offset_ms)
        return adjusted.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    async def _sync_server_time(self) -> None:
        """同步 OKX 服务器时间，计算本机与服务器的时间偏移

        OKX 要求时间戳与服务器偏差不超过 30 秒，否则返回错误码 50102。
        首次请求前调用此方法校准，避免因系统时钟偏差导致认证失败。
        """
        try:
            client = await self.get_shared_client()
            resp = await client.get(f"{self.BASE_URL}/api/v5/public/time")
            resp.raise_for_status()
            data = resp.json()
            server_ts = int(data["data"][0]["ts"])  # 服务器毫秒时间戳
            local_ts = int(time.time() * 1000)
            self._time_offset_ms = server_ts - local_ts
            self._time_synced = True
            logger.info(
                "[OKXAdapter] 服务器时间同步完成，偏移: %dms",
                self._time_offset_ms,
            )
        except Exception as exc:
            logger.warning("[OKXAdapter] 服务器时间同步失败: %s", exc)
            # 同步失败不阻塞，用本机时间继续

    def _sign(self, method: str, path: str, body: str = "") -> dict[str, str]:
        """OKX HMAC SHA256 签名

        签名内容: timestamp + method + requestPath + body
        签名方式: HMAC-SHA256(secret, message) → Base64
        """
        timestamp = self._okx_timestamp()
        message = timestamp + method.upper() + path + body
        mac = hmac.new(
            self.secret_key.encode(), message.encode(), hashlib.sha256
        )
        sign = base64.b64encode(mac.digest()).decode()
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase or "",
            "Content-Type": "application/json",
        }
        # OKX 要求 passphrase 不能为空，空字符串会导致 50113 错误
        if not self.passphrase:
            logger.error(
                "[OKXAdapter] OK-ACCESS-PASSPHRASE 为空字符串，"
                "OKX 认证必定失败。请确保添加 OKX 账户时填写了 Passphrase。"
            )
        if self.is_demo:
            headers["x-simulated-trading"] = "1"
        return headers

    async def _ensure_time_synced(self) -> None:
        """确保已与 OKX 服务器同步时间（仅首次调用时执行）"""
        if not self._time_synced:
            await self._sync_server_time()

    def _check_okx_response(self, data: dict) -> None:
        """检查 OKX 响应，code != 0 为错误

        OKX 错误码分类：
        - 5xxxx: 系统错误（可重试）
        - 51001/51002/51006: 参数错误（不可重试）
        - 51400: 余额不足（不可重试）
        - 51503: 订单不存在（不可重试）
        """
        code = data.get("code", "")
        if code != "0":
            msg = data.get("msg", "Unknown error")
            reject_codes = {"51001", "51002", "51006", "51400", "51503"}
            if code in reject_codes:
                raise OrderRejectedError("OKX", f"[{code}] {msg}", detail_code=code)
            raise ExchangeAPIError("OKX", f"[{code}] {msg}", detail_code=code)

    # ---- 行情接口 ----

    async def get_ticker(self, symbol: str) -> Ticker:
        inst_id = self._to_inst_id(symbol)

        async def _do():
            client = await self.get_shared_client()
            resp = await client.get(
                f"{self.BASE_URL}/api/v5/market/ticker",
                params={"instId": inst_id},
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_ticker({symbol})")
        self._check_okx_response(data)
        t = data["data"][0]
        open_price = _safe_decimal(t.get("open24h"))
        last_price = _safe_decimal(t.get("last"))
        price_change_pct = _safe_divide(
            (last_price - open_price) * 100, open_price, Decimal("0")
        )
        return Ticker(
            symbol=symbol,
            price=last_price,
            price_change=last_price - open_price,
            price_change_percent=price_change_pct or Decimal("0"),
            high_24h=_safe_decimal(t.get("high24h")),
            low_24h=_safe_decimal(t.get("low24h")),
            volume_24h=_safe_decimal(t.get("vol24h")),
            quote_volume_24h=_safe_decimal(t.get("volCcy24h")),
            timestamp=datetime.fromtimestamp(
                _safe_decimal(t.get("ts")) / 1000, tz=timezone.utc
            ),
        )

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 100
    ) -> list[Kline]:
        inst_id = self._to_inst_id(symbol)

        async def _do():
            client = await self.get_shared_client()
            resp = await client.get(
                f"{self.BASE_URL}/api/v5/market/candles",
                params={"instId": inst_id, "bar": interval, "limit": str(limit)},
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_klines({symbol})")
        self._check_okx_response(data)
        klines = []
        for k in data.get("data", []):
            klines.append(Kline(
                timestamp=datetime.fromtimestamp(_safe_decimal(k[0]) / 1000, tz=timezone.utc),
                open=_safe_decimal(k[1]),
                high=_safe_decimal(k[2]),
                low=_safe_decimal(k[3]),
                close=_safe_decimal(k[4]),
                volume=_safe_decimal(k[5]),
                close_time=datetime.fromtimestamp(_safe_decimal(k[6]) / 1000, tz=timezone.utc),
            ))
        return klines

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        inst_id = self._to_inst_id(symbol)

        async def _do():
            client = await self.get_shared_client()
            resp = await client.get(
                f"{self.BASE_URL}/api/v5/market/books",
                params={"instId": inst_id, "sz": str(limit)},
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_orderbook({symbol})")
        self._check_okx_response(data)
        books = data["data"][0] if data.get("data") else {}
        return OrderBook(
            bids=[(_safe_decimal(p), _safe_decimal(q)) for p, q, *_ in books.get("bids", [])],
            asks=[(_safe_decimal(p), _safe_decimal(q)) for p, q, *_ in books.get("asks", [])],
        )

    # ---- 交易接口 ----

    async def get_balance(self) -> list[Balance]:
        """获取账户余额"""
        await self._ensure_time_synced()
        path = "/api/v5/account/balance"

        async def _do():
            headers = self._sign("GET", path)
            client = await self.get_shared_client()
            resp = await client.get(f"{self.BASE_URL}{path}", headers=headers)
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context="get_balance")
        self._check_okx_response(data)

        balances = []
        for detail in data.get("data", []):
            for b in detail.get("details", []):
                free = _safe_decimal(b.get("availBal"))
                locked = _safe_decimal(b.get("frozenBal"))
                if free > 0 or locked > 0:
                    balances.append(Balance(
                        asset=b.get("ccy", ""),
                        free=free,
                        locked=locked,
                    ))
        return balances

    async def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        """获取持仓（合约用，现货返回空列表）"""
        await self._ensure_time_synced()
        path = "/api/v5/account/positions"
        params = {}
        if symbol:
            params["instId"] = self._to_inst_id(symbol)
        if params:
            path += "?" + urlencode(params)

        async def _do():
            headers = self._sign("GET", path)
            client = await self.get_shared_client()
            resp = await client.get(f"{self.BASE_URL}{path}", headers=headers)
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_positions({symbol})")
        self._check_okx_response(data)

        positions = []
        for p in data.get("data", []):
            positions.append(PositionInfo(
                symbol=p.get("instId", ""),
                side=p.get("posSide", "net"),
                quantity=_safe_decimal(p.get("pos")),
                entry_price=_safe_decimal(p.get("avgPx")),
                current_price=_safe_decimal(p.get("markPx")),
                unrealized_pnl=_safe_decimal(p.get("upl")),
                leverage=int(_safe_decimal(p.get("lever"), Decimal("1"))),
            ))
        return positions

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
    ) -> OrderResult:
        """创建订单

        OKX POST /api/v5/trade/order
        - tdMode: cash (现货) / cross (全仓) / isolated (逐仓)
        - ordType: market / limit / post_only / fok / ioc
        """
        inst_id = self._to_inst_id(symbol)
        await self._ensure_time_synced()
        path = "/api/v5/trade/order"
        body_dict: dict[str, Any] = {
            "instId": inst_id,
            "tdMode": "cash",
            "side": side.lower(),
            "ordType": order_type.lower() if order_type.lower() in ("market", "limit", "post_only", "fok", "ioc") else "limit",
            "sz": str(quantity),
        }
        if price and order_type.lower() == "limit":
            body_dict["px"] = str(price)

        body_json = json.dumps(body_dict)

        async def _do():
            headers = self._sign("POST", path, body_json)
            client = await self.get_shared_client()
            resp = await client.post(
                f"{self.BASE_URL}{path}",
                headers=headers,
                content=body_json,
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(
            _do, max_attempts=1,  # 下单不重试
            context=f"create_order({symbol},{side},{order_type})",
        )
        self._check_okx_response(data)

        order_data = data["data"][0]
        s_code = order_data.get("sCode", "")
        if s_code != "0":
            # OKX 下单错误码
            raise OrderRejectedError(
                "OKX", f"[{s_code}] {order_data.get('sMsg')}",
                detail_code=s_code,
            )

        return OrderResult(
            exchange_order_id=order_data.get("ordId", ""),
            symbol=symbol,
            side=side.lower(),
            order_type=order_type.lower(),
            quantity=quantity,
            price=price,
            status="pending",  # 刚下单，状态未知
            filled_quantity=Decimal("0"),
            avg_fill_price=None,
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        inst_id = self._to_inst_id(symbol)
        await self._ensure_time_synced()
        path = "/api/v5/trade/cancel-order"
        body_dict = {"instId": inst_id, "ordId": order_id}
        body_json = json.dumps(body_dict)

        async def _do():
            headers = self._sign("POST", path, body_json)
            client = await self.get_shared_client()
            resp = await client.post(
                f"{self.BASE_URL}{path}",
                headers=headers,
                content=body_json,
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(
            _do, max_attempts=2,
            context=f"cancel_order({symbol},{order_id})",
        )
        self._check_okx_response(data)

        order_data = data["data"][0]
        return order_data.get("sCode") == "0"

    async def get_order(self, order_id: str, symbol: str) -> OrderResult:
        """查询订单状态"""
        await self._ensure_time_synced()
        inst_id = self._to_inst_id(symbol)
        path = f"/api/v5/trade/order?instId={inst_id}&ordId={order_id}"

        async def _do():
            headers = self._sign("GET", path)
            client = await self.get_shared_client()
            resp = await client.get(f"{self.BASE_URL}{path}", headers=headers)
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_order({symbol},{order_id})")
        self._check_okx_response(data)

        o = data["data"][0]
        avg_price = _safe_decimal(o.get("avgPx"))
        filled = _safe_decimal(o.get("fillSz"))

        return OrderResult(
            exchange_order_id=o.get("ordId", ""),
            symbol=symbol,
            side=o.get("side", "buy").lower(),
            order_type=o.get("ordType", "market").lower(),
            quantity=_safe_decimal(o.get("sz")),
            price=_safe_decimal(o.get("px")) if _safe_decimal(o.get("px")) > 0 else None,
            status=_OKX_STATUS_MAP.get(o.get("state", ""), "pending"),
            filled_quantity=filled,
            avg_fill_price=avg_price if avg_price > 0 else None,
        )


# ==================== Huobi 适配器 ====================

class HuobiAdapter(BaseExchangeAdapter):
    """Huobi (HTX) 交易所适配器

    API 文档: https://huobiapi.github.io/docs/spot/v1/cn/
    签名: HMAC SHA256，method\\nhost\\npath\\nparams → Base64
    参数: AccessKeyId / SignatureMethod / SignatureVersion / Timestamp / Signature
    """

    BASE_URL = "https://api.huobi.pro"

    # Huobi 限流：10 requests/second
    RATE_LIMIT_INTERVAL = 0.1

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str | None = None,
    ):
        super().__init__(api_key, secret_key, passphrase)
        self._account_id: str | None = None
        self._account_id_fetched_at: float = 0.0  # 缓存时间戳
        self._ACCOUNT_ID_TTL = 300.0  # 缓存有效期 5 分钟

    def _invalidate_account_id_cache(self) -> None:
        """清理 accountId 缓存，下次请求时重新获取"""
        logger.info("[HuobiAdapter] 清理 accountId 缓存")
        self._account_id = None
        self._account_id_fetched_at = 0.0

    def _to_huobi_symbol(self, symbol: str) -> str:
        """转换 symbol 为 Huobi 格式: btcusdt"""
        return symbol.lower()

    def _sign_params(self, method: str, path: str, params: dict | None = None) -> dict:
        """Huobi HMAC SHA256 签名

        签名内容: METHOD\\nhost\\npath\\nsorted_query_string
        签名方式: HMAC-SHA256(secret, message) → Base64
        """
        params = params or {}
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        sign_params = {
            "AccessKeyId": self.api_key,
            "SignatureMethod": "HmacSHA256",
            "SignatureVersion": "2",
            "Timestamp": timestamp,
            **params,
        }
        # 按键排序
        sorted_params = sorted(sign_params.items())
        query_string = urlencode(sorted_params)
        host = self.BASE_URL.replace("https://", "").replace("http://", "")
        payload = f"{method.upper()}\n{host}\n{path}\n{query_string}"
        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode(), payload.encode(), hashlib.sha256
            ).digest()
        ).decode()
        sign_params["Signature"] = signature
        return sign_params

    async def _get_account_id(self) -> str:
        """获取 Huobi 账户 ID（下单必需，懒加载缓存 + TTL 失效）

        缓存策略：
        - 首次调用时获取并缓存
        - TTL 5 分钟后自动失效
        - 下单失败时由调用方清理缓存
        """
        now = time.monotonic()
        if self._account_id and (now - self._account_id_fetched_at < self._ACCOUNT_ID_TTL):
            return self._account_id

        logger.info("[HuobiAdapter] 获取 accountId（缓存未命中或已过期）")

        async def _do():
            path = "/v1/account/accounts"
            params = self._sign_params("GET", path)
            client = await self.get_shared_client()
            resp = await client.get(f"{self.BASE_URL}{path}", params=params)
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context="get_account_id")

        if data.get("status") != "ok":
            err_msg = data.get("err-msg", "获取账户ID失败")
            err_code = data.get("err-code", "unknown")
            raise ExchangeAPIError("Huobi", f"[{err_code}] {err_msg}", detail_code=err_code)

        # 优先选 spot 账户，其次选第一个账户
        for account in data.get("data", []):
            if account.get("type") == "spot":
                self._account_id = str(account["id"])
                self._account_id_fetched_at = time.monotonic()
                logger.info(
                    "[HuobiAdapter] accountId 获取成功: id=%s, type=spot",
                    self._account_id,
                )
                return self._account_id

        # 降级：选第一个可用账户
        if data.get("data"):
            first = data["data"][0]
            self._account_id = str(first["id"])
            self._account_id_fetched_at = time.monotonic()
            logger.warning(
                "[HuobiAdapter] 未找到 spot 账户，使用第一个账户: id=%s, type=%s",
                self._account_id, first.get("type"),
            )
            return self._account_id

        raise ExchangeAPIError("Huobi", "未找到任何账户")

    def _check_huobi_response(self, data: dict) -> None:
        """检查 Huobi 响应"""
        if data.get("status") != "ok":
            err_msg = data.get("err-msg", "Unknown error")
            err_code = data.get("err-code", "unknown")
            # Huobi 拒单相关错误码
            reject_codes = {
                "order-invalid-order-price",
                "order-invalid-order-amount",
                "insufficient-balance",
                "invalid-account-id",
                "order-limitorder-amount-min-error",
            }
            if err_code in reject_codes:
                raise OrderRejectedError("Huobi", f"[{err_code}] {err_msg}", detail_code=err_code)
            raise ExchangeAPIError("Huobi", f"[{err_code}] {err_msg}", detail_code=err_code)

    # ---- 行情接口 ----

    async def get_ticker(self, symbol: str) -> Ticker:
        huobi_symbol = self._to_huobi_symbol(symbol)

        async def _do():
            client = await self.get_shared_client()
            resp = await client.get(
                f"{self.BASE_URL}/market/detail/merged",
                params={"symbol": huobi_symbol},
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_ticker({symbol})")
        if data.get("status") != "ok":
            raise ExchangeAPIError("Huobi", data.get("err-msg", "获取行情失败"))

        tick = data["tick"]
        close = _safe_decimal(tick.get("close"))
        open_price = _safe_decimal(tick.get("open"))
        price_change_pct = _safe_divide(
            (close - open_price) * 100, open_price, Decimal("0")
        )
        return Ticker(
            symbol=symbol,
            price=close,
            price_change=close - open_price,
            price_change_percent=price_change_pct or Decimal("0"),
            high_24h=_safe_decimal(tick.get("high")),
            low_24h=_safe_decimal(tick.get("low")),
            volume_24h=_safe_decimal(tick.get("vol")),
            quote_volume_24h=_safe_decimal(tick.get("amount")),
            timestamp=datetime.fromtimestamp(
                _safe_decimal(tick.get("version")) / 1000, tz=timezone.utc
            ),
        )

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 100
    ) -> list[Kline]:
        """获取K线数据

        Huobi period 格式: 1min/5min/15min/30min/60min/4hour/1day/1week
        """
        huobi_symbol = self._to_huobi_symbol(symbol)
        # 转换 interval 为 Huobi 格式
        period_map = {
            "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
            "1h": "60min", "4h": "4hour", "1d": "1day", "1w": "1week",
        }
        period = period_map.get(interval, "60min")

        async def _do():
            client = await self.get_shared_client()
            resp = await client.get(
                f"{self.BASE_URL}/market/history/kline",
                params={"symbol": huobi_symbol, "period": period, "size": str(limit)},
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_klines({symbol})")
        if data.get("status") != "ok":
            raise ExchangeAPIError("Huobi", data.get("err-msg", "获取K线失败"))

        klines = []
        for k in data.get("data", []):
            klines.append(Kline(
                timestamp=datetime.fromtimestamp(_safe_decimal(k.get("id")), tz=timezone.utc),
                open=_safe_decimal(k.get("open")),
                high=_safe_decimal(k.get("high")),
                low=_safe_decimal(k.get("low")),
                close=_safe_decimal(k.get("close")),
                volume=_safe_decimal(k.get("vol")),
                close_time=datetime.fromtimestamp(
                    _safe_decimal(k.get("id")) + 60, tz=timezone.utc
                ),
            ))
        return klines

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        huobi_symbol = self._to_huobi_symbol(symbol)
        depth_type = "step0"

        async def _do():
            client = await self.get_shared_client()
            resp = await client.get(
                f"{self.BASE_URL}/market/depth",
                params={"symbol": huobi_symbol, "type": depth_type, "depth": str(limit)},
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_orderbook({symbol})")
        if data.get("status") != "ok":
            raise ExchangeAPIError("Huobi", data.get("err-msg", "获取订单簿失败"))

        tick = data.get("tick", {})
        return OrderBook(
            bids=[(_safe_decimal(p), _safe_decimal(q)) for p, q in tick.get("bids", [])],
            asks=[(_safe_decimal(p), _safe_decimal(q)) for p, q in tick.get("asks", [])],
        )

    # ---- 交易接口 ----

    async def get_balance(self) -> list[Balance]:
        """获取现货账户余额"""
        account_id = await self._get_account_id()
        path = f"/v1/account/accounts/{account_id}/balance"

        async def _do():
            params = self._sign_params("GET", path)
            client = await self.get_shared_client()
            resp = await client.get(f"{self.BASE_URL}{path}", params=params)
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context="get_balance")
        self._check_huobi_response(data)

        balances = []
        for b in data.get("data", {}).get("list", []):
            free = _safe_decimal(b.get("balance"))
            if b.get("type") == "trade":
                balances.append(Balance(
                    asset=b.get("currency", "").upper(),
                    free=free,
                    locked=Decimal("0"),
                ))
            elif b.get("type") == "frozen":
                # 找到对应的 trade 记录并更新 locked
                for existing in balances:
                    if existing.asset == b.get("currency", "").upper():
                        existing.locked = _safe_decimal(b.get("balance"))
                        break
                else:
                    balances.append(Balance(
                        asset=b.get("currency", "").upper(),
                        free=Decimal("0"),
                        locked=_safe_decimal(b.get("balance")),
                    ))
        # 过滤零余额
        return [b for b in balances if b.free > 0 or b.locked > 0]

    async def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        """现货无持仓，返回空列表"""
        return []

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
    ) -> OrderResult:
        """创建订单

        Huobi POST /v1/order/orders/place
        - type: buy-market / sell-market / buy-limit / sell-limit
        - 需要 account-id（自动获取）
        - 下单失败时自动清理 accountId 缓存
        """
        try:
            account_id = await self._get_account_id()
        except ExchangeAPIError:
            self._invalidate_account_id_cache()
            # 重试一次获取 accountId
            account_id = await self._get_account_id()

        huobi_symbol = self._to_huobi_symbol(symbol)
        huobi_type = f"{side.lower()}-{order_type.lower()}"
        path = "/v1/order/orders/place"
        body_dict: dict[str, Any] = {
            "account-id": account_id,
            "symbol": huobi_symbol,
            "type": huobi_type,
            "amount": f"{quantity:.8f}".rstrip("0").rstrip("."),
            "source": "spot-api",
        }
        if price and order_type.lower() == "limit":
            body_dict["price"] = f"{price:.8f}".rstrip("0").rstrip(".")

        async def _do():
            params = self._sign_params("POST", path)
            client = await self.get_shared_client()
            resp = await client.post(
                f"{self.BASE_URL}{path}",
                params=params,
                json=body_dict,
            )
            resp.raise_for_status()
            return resp.json()

        try:
            data = await self._request_with_retry(
                _do, max_attempts=1,  # 下单不重试
                context=f"create_order({symbol},{side},{order_type})",
            )
        except ExchangeAPIError as exc:
            # accountId 无效时清理缓存，方便下次重新获取
            if exc.detail_code == "invalid-account-id" or "account" in str(exc.message).lower():
                self._invalidate_account_id_cache()
                logger.warning(
                    "[HuobiAdapter] 下单失败，可能 accountId 失效，已清理缓存: %s",
                    exc.message,
                )
            raise

        self._check_huobi_response(data)

        return OrderResult(
            exchange_order_id=str(data.get("data", "")),
            symbol=symbol,
            side=side.lower(),
            order_type=order_type.lower(),
            quantity=quantity,
            price=price,
            status="pending",
            filled_quantity=Decimal("0"),
            avg_fill_price=None,
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        path = f"/v1/order/orders/{order_id}/submitcancel"

        async def _do():
            params = self._sign_params("POST", path)
            client = await self.get_shared_client()
            resp = await client.post(
                f"{self.BASE_URL}{path}",
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(
            _do, max_attempts=2,
            context=f"cancel_order({symbol},{order_id})",
        )
        self._check_huobi_response(data)
        return str(data.get("data", "")) == order_id

    async def get_order(self, order_id: str, symbol: str) -> OrderResult:
        """查询订单状态"""
        path = f"/v1/order/orders/{order_id}"

        async def _do():
            params = self._sign_params("GET", path)
            client = await self.get_shared_client()
            resp = await client.get(f"{self.BASE_URL}{path}", params=params)
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_order({symbol},{order_id})")
        self._check_huobi_response(data)

        o = data.get("data", {})
        filled_qty = _safe_decimal(o.get("field-amount"))
        field_cash = _safe_decimal(o.get("field-cash-amount"))
        avg_price = _safe_divide(field_cash, filled_qty)

        order_type_str = o.get("type", "buy-market")
        parts = order_type_str.split("-")
        side = parts[0] if len(parts) >= 1 else "buy"
        otype = parts[1] if len(parts) >= 2 else "market"

        return OrderResult(
            exchange_order_id=str(o.get("id", "")),
            symbol=o.get("symbol", symbol).upper(),
            side=side,
            order_type=otype,
            quantity=_safe_decimal(o.get("amount")),
            price=_safe_decimal(o.get("price")) if _safe_decimal(o.get("price")) > 0 else None,
            status=_HUOBI_STATUS_MAP.get(o.get("state", ""), "pending"),
            filled_quantity=filled_qty,
            avg_fill_price=avg_price,
        )


# ==================== 工厂函数 ====================

def get_exchange_adapter(
    exchange: str,
    api_key: str,
    secret_key: str,
    passphrase: str | None = None,
    testnet: bool = False,
    is_demo: bool = False,
) -> BaseExchangeAdapter:
    """获取交易所适配器

    Args:
        exchange: 交易所名称 (binance/okx/huobi/htx)
        api_key: API Key（明文）
        secret_key: Secret Key（明文）
        passphrase: OKX 的 passphrase
        testnet: Binance 测试网
        is_demo: OKX 模拟盘

    Returns:
        BaseExchangeAdapter 实例

    注意:
        - testnet/is_demo 应从 ExchangeAccount 配置中获取
        - 生产环境务必确认这两个标志正确设置
    """
    exchange_lower = exchange.lower()
    adapters: dict[str, type[BaseExchangeAdapter]] = {
        "binance": BinanceAdapter,
        "okx": OKXAdapter,
        "huobi": HuobiAdapter,
        "htx": HuobiAdapter,  # HTX 是 Huobi 新名
    }

    adapter_class = adapters.get(exchange_lower)
    if not adapter_class:
        raise ValueError(f"不支持的交易所: {exchange}")

    if adapter_class == BinanceAdapter:
        if testnet:
            logger.info("[Factory] 创建 Binance testnet 适配器")
        return BinanceAdapter(api_key, secret_key, passphrase, testnet=testnet)
    elif adapter_class == OKXAdapter:
        if is_demo:
            logger.info("[Factory] 创建 OKX 模拟盘适配器 (x-simulated-trading=1)")
        return OKXAdapter(api_key, secret_key, passphrase, is_demo=is_demo)
    else:
        return adapter_class(api_key, secret_key, passphrase)
