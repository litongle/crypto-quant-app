"""
交易所适配器 - 统一接口 + 三大交易所实现

架构：
- 全异步 httpx.AsyncClient 单例复用（PRF-01）
- HMAC SHA256 签名认证
- 统一数据模型（Ticker/Kline/OrderBook/Balance/OrderResult/PositionInfo）
- 支持交易所：Binance / OKX / Huobi
"""
import base64
import hashlib
import hmac
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.exceptions import ExchangeAPIError

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str | None = None,
        testnet: bool = False,
    ):
        super().__init__(api_key, secret_key, passphrase)
        self.base_url = self.TESTNET_URL if testnet else self.BASE_URL

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
            raise ExchangeAPIError(exchange=exchange, message=f"[{data['code']}] {msg}")

    # ---- 行情接口 ----

    async def get_ticker(self, symbol: str) -> Ticker:
        client = await self.get_shared_client()
        resp = await client.get(
            f"{self.base_url}/api/v3/ticker/24hr",
            params={"symbol": symbol},
        )
        data = resp.json()
        self._check_response(data)
        return Ticker(
            symbol=data["symbol"],
            price=Decimal(data["lastPrice"]),
            price_change=Decimal(data["priceChange"]),
            price_change_percent=Decimal(data["priceChangePercent"]),
            high_24h=Decimal(data["highPrice"]),
            low_24h=Decimal(data["lowPrice"]),
            volume_24h=Decimal(data["volume"]),
            quote_volume_24h=Decimal(data["quoteVolume"]),
            timestamp=datetime.fromtimestamp(data["closeTime"] / 1000, tz=timezone.utc),
        )

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 100
    ) -> list[Kline]:
        client = await self.get_shared_client()
        resp = await client.get(
            f"{self.base_url}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        klines = []
        for k in resp.json():
            klines.append(Kline(
                timestamp=datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
                open=Decimal(k[1]),
                high=Decimal(k[2]),
                low=Decimal(k[3]),
                close=Decimal(k[4]),
                volume=Decimal(k[5]),
                close_time=datetime.fromtimestamp(k[6] / 1000, tz=timezone.utc),
            ))
        return klines

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        client = await self.get_shared_client()
        resp = await client.get(
            f"{self.base_url}/api/v3/depth",
            params={"symbol": symbol, "limit": limit},
        )
        data = resp.json()
        return OrderBook(
            bids=[(Decimal(p), Decimal(q)) for p, q in data["bids"]],
            asks=[(Decimal(p), Decimal(q)) for p, q in data["asks"]],
        )

    # ---- 交易接口 ----

    async def get_balance(self) -> list[Balance]:
        """获取现货账户余额（过滤零余额）"""
        client = await self.get_shared_client()
        params = self._sign_params({})
        resp = await client.get(
            f"{self.base_url}/api/v3/account",
            params=params,
            headers=self._auth_headers(),
        )
        data = resp.json()
        self._check_response(data)
        balances = []
        for b in data.get("balances", []):
            free = Decimal(b["free"])
            locked = Decimal(b["locked"])
            if free > 0 or locked > 0:
                balances.append(Balance(
                    asset=b["asset"],
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
        client = await self.get_shared_client()
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": f"{quantity:.8f}".rstrip("0").rstrip("."),
        }
        if order_type.lower() == "limit":
            if price is None:
                raise ExchangeAPIError("Binance", "限价单必须指定价格")
            params["price"] = f"{price:.8f}".rstrip("0").rstrip(".")
            params["timeInForce"] = "GTC"

        params = self._sign_params(params)
        resp = await client.post(
            f"{self.base_url}/api/v3/order",
            params=params,
            headers=self._auth_headers(),
        )
        data = resp.json()
        self._check_response(data)

        return OrderResult(
            exchange_order_id=str(data["orderId"]),
            symbol=data["symbol"],
            side=data["side"].lower(),
            order_type=data["type"].lower(),
            quantity=Decimal(data["origQty"]),
            price=Decimal(data["price"]) if Decimal(data.get("price", "0")) > 0 else None,
            status=_BINANCE_STATUS_MAP.get(data["status"], "pending"),
            filled_quantity=Decimal(data["executedQty"]),
            avg_fill_price=(
                Decimal(data["cummulativeQuoteQty"]) / Decimal(data["executedQty"])
                if Decimal(data["executedQty"]) > 0 and Decimal(data.get("cummulativeQuoteQty", "0")) > 0
                else None
            ),
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
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
        data = resp.json()
        self._check_response(data)
        return data.get("status") in ("CANCELED", "CANCELLED")

    async def get_order(self, order_id: str, symbol: str) -> OrderResult:
        """查询订单状态"""
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
        data = resp.json()
        self._check_response(data)

        return OrderResult(
            exchange_order_id=str(data["orderId"]),
            symbol=data["symbol"],
            side=data["side"].lower(),
            order_type=data["type"].lower(),
            quantity=Decimal(data["origQty"]),
            price=Decimal(data["price"]) if Decimal(data.get("price", "0")) > 0 else None,
            status=_BINANCE_STATUS_MAP.get(data["status"], "pending"),
            filled_quantity=Decimal(data["executedQty"]),
            avg_fill_price=(
                Decimal(data["cummulativeQuoteQty"]) / Decimal(data["executedQty"])
                if Decimal(data["executedQty"]) > 0 and Decimal(data.get("cummulativeQuoteQty", "0")) > 0
                else None
            ),
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

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str | None = None,
        is_demo: bool = False,
    ):
        super().__init__(api_key, secret_key, passphrase)
        self.is_demo = is_demo

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
        """OKX 要求的 ISO 8601 时间戳（毫秒级）"""
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

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
        if self.is_demo:
            headers["x-simulated-trading"] = "1"
        return headers

    def _check_okx_response(self, data: dict) -> None:
        """检查 OKX 响应，code != 0 为错误"""
        if data.get("code") != "0":
            msg = data.get("msg", "Unknown error")
            raise ExchangeAPIError("OKX", f"[{data.get('code')}] {msg}")

    # ---- 行情接口 ----

    async def get_ticker(self, symbol: str) -> Ticker:
        inst_id = self._to_inst_id(symbol)
        client = await self.get_shared_client()
        resp = await client.get(
            f"{self.BASE_URL}/api/v5/market/ticker",
            params={"instId": inst_id},
        )
        data = resp.json()
        self._check_okx_response(data)
        t = data["data"][0]
        open_price = Decimal(t["open24h"])
        last_price = Decimal(t["last"])
        return Ticker(
            symbol=symbol,
            price=last_price,
            price_change=last_price - open_price,
            price_change_percent=(
                (last_price - open_price) / open_price * 100
                if open_price > 0 else Decimal("0")
            ),
            high_24h=Decimal(t["high24h"]),
            low_24h=Decimal(t["low24h"]),
            volume_24h=Decimal(t["vol24h"]),
            quote_volume_24h=Decimal(t["volCcy24h"]),
            timestamp=datetime.fromtimestamp(int(t["ts"]) / 1000, tz=timezone.utc),
        )

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 100
    ) -> list[Kline]:
        inst_id = self._to_inst_id(symbol)
        client = await self.get_shared_client()
        resp = await client.get(
            f"{self.BASE_URL}/api/v5/market/candles",
            params={"instId": inst_id, "bar": interval, "limit": str(limit)},
        )
        data = resp.json()
        self._check_okx_response(data)
        klines = []
        for k in data["data"]:
            klines.append(Kline(
                timestamp=datetime.fromtimestamp(int(k[0]) / 1000, tz=timezone.utc),
                open=Decimal(k[1]),
                high=Decimal(k[2]),
                low=Decimal(k[3]),
                close=Decimal(k[4]),
                volume=Decimal(k[5]),
                close_time=datetime.fromtimestamp(int(k[6]) / 1000, tz=timezone.utc),
            ))
        return klines

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        inst_id = self._to_inst_id(symbol)
        client = await self.get_shared_client()
        resp = await client.get(
            f"{self.BASE_URL}/api/v5/market/books",
            params={"instId": inst_id, "sz": str(limit)},
        )
        data = resp.json()
        self._check_okx_response(data)
        books = data["data"][0]
        return OrderBook(
            bids=[(Decimal(p), Decimal(q)) for p, q, *_ in books.get("bids", [])],
            asks=[(Decimal(p), Decimal(q)) for p, q, *_ in books.get("asks", [])],
        )

    # ---- 交易接口 ----

    async def get_balance(self) -> list[Balance]:
        """获取账户余额"""
        path = "/api/v5/account/balance"
        headers = self._sign("GET", path)
        client = await self.get_shared_client()
        resp = await client.get(f"{self.BASE_URL}{path}", headers=headers)
        data = resp.json()
        self._check_okx_response(data)

        balances = []
        for detail in data["data"]:
            for b in detail.get("details", []):
                free = Decimal(b.get("availBal", "0"))
                locked = Decimal(b.get("frozenBal", "0"))
                if free > 0 or locked > 0:
                    balances.append(Balance(
                        asset=b["ccy"],
                        free=free,
                        locked=locked,
                    ))
        return balances

    async def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        """获取持仓（合约用，现货返回空列表）"""
        path = "/api/v5/account/positions"
        params = {}
        if symbol:
            params["instId"] = self._to_inst_id(symbol)
        if params:
            path += "?" + urlencode(params)

        headers = self._sign("GET", path)
        client = await self.get_shared_client()
        resp = await client.get(f"{self.BASE_URL}{path}", headers=headers)
        data = resp.json()
        self._check_okx_response(data)

        positions = []
        for p in data["data"]:
            positions.append(PositionInfo(
                symbol=p["instId"],
                side=p["posSide"],
                quantity=Decimal(p["pos"]),
                entry_price=Decimal(p["avgPx"]),
                current_price=Decimal(p["markPx"]),
                unrealized_pnl=Decimal(p["upl"]),
                leverage=int(Decimal(p["lever"])),
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
        headers = self._sign("POST", path, body_json)
        client = await self.get_shared_client()
        resp = await client.post(
            f"{self.BASE_URL}{path}",
            headers=headers,
            content=body_json,
        )
        data = resp.json()
        self._check_okx_response(data)

        order_data = data["data"][0]
        if order_data.get("sCode") != "0":
            raise ExchangeAPIError("OKX", f"[{order_data.get('sCode')}] {order_data.get('sMsg')}")

        return OrderResult(
            exchange_order_id=order_data["ordId"],
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
        path = "/api/v5/trade/cancel-order"
        body_dict = {"instId": inst_id, "ordId": order_id}
        body_json = json.dumps(body_dict)
        headers = self._sign("POST", path, body_json)

        client = await self.get_shared_client()
        resp = await client.post(
            f"{self.BASE_URL}{path}",
            headers=headers,
            content=body_json,
        )
        data = resp.json()
        self._check_okx_response(data)

        order_data = data["data"][0]
        return order_data.get("sCode") == "0"

    async def get_order(self, order_id: str, symbol: str) -> OrderResult:
        """查询订单状态"""
        inst_id = self._to_inst_id(symbol)
        path = f"/api/v5/trade/order?instId={inst_id}&ordId={order_id}"
        headers = self._sign("GET", path)

        client = await self.get_shared_client()
        resp = await client.get(f"{self.BASE_URL}{path}", headers=headers)
        data = resp.json()
        self._check_okx_response(data)

        o = data["data"][0]
        avg_price = Decimal(o.get("avgPx", "0"))
        filled = Decimal(o.get("fillSz", "0"))

        return OrderResult(
            exchange_order_id=o["ordId"],
            symbol=symbol,
            side=o["side"].lower(),
            order_type=o["ordType"].lower(),
            quantity=Decimal(o["sz"]),
            price=Decimal(o["px"]) if Decimal(o.get("px", "0")) > 0 else None,
            status=_OKX_STATUS_MAP.get(o["state"], "pending"),
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

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str | None = None,
    ):
        super().__init__(api_key, secret_key, passphrase)
        self._account_id: str | None = None

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
        """获取 Huobi 账户 ID（下单必需，懒加载缓存）"""
        if self._account_id:
            return self._account_id

        path = "/v1/account/accounts"
        params = self._sign_params("GET", path)
        client = await self.get_shared_client()
        resp = await client.get(f"{self.BASE_URL}{path}", params=params)
        data = resp.json()

        if data.get("status") != "ok":
            raise ExchangeAPIError("Huobi", data.get("err-msg", "获取账户ID失败"))

        for account in data.get("data", []):
            if account.get("type") == "spot":
                self._account_id = str(account["id"])
                return self._account_id

        raise ExchangeAPIError("Huobi", "未找到现货账户")

    def _check_huobi_response(self, data: dict) -> None:
        """检查 Huobi 响应"""
        if data.get("status") != "ok":
            err_msg = data.get("err-msg", "Unknown error")
            err_code = data.get("err-code", "unknown")
            raise ExchangeAPIError("Huobi", f"[{err_code}] {err_msg}")

    # ---- 行情接口 ----

    async def get_ticker(self, symbol: str) -> Ticker:
        huobi_symbol = self._to_huobi_symbol(symbol)
        client = await self.get_shared_client()
        resp = await client.get(
            f"{self.BASE_URL}/market/detail/merged",
            params={"symbol": huobi_symbol},
        )
        data = resp.json()
        if data.get("status") != "ok":
            raise ExchangeAPIError("Huobi", data.get("err-msg", "获取行情失败"))

        tick = data["tick"]
        close = Decimal(tick["close"])
        open_price = Decimal(tick["open"])
        return Ticker(
            symbol=symbol,
            price=close,
            price_change=close - open_price,
            price_change_percent=(
                (close - open_price) / open_price * 100
                if open_price > 0 else Decimal("0")
            ),
            high_24h=Decimal(tick["high"]),
            low_24h=Decimal(tick["low"]),
            volume_24h=Decimal(tick["vol"]),
            quote_volume_24h=Decimal(tick["amount"]),
            timestamp=datetime.fromtimestamp(tick["version"] / 1000, tz=timezone.utc),
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

        client = await self.get_shared_client()
        resp = await client.get(
            f"{self.BASE_URL}/market/history/kline",
            params={"symbol": huobi_symbol, "period": period, "size": str(limit)},
        )
        data = resp.json()
        if data.get("status") != "ok":
            raise ExchangeAPIError("Huobi", data.get("err-msg", "获取K线失败"))

        klines = []
        for k in data["data"]:
            klines.append(Kline(
                timestamp=datetime.fromtimestamp(k["id"], tz=timezone.utc),
                open=Decimal(str(k["open"])),
                high=Decimal(str(k["high"])),
                low=Decimal(str(k["low"])),
                close=Decimal(str(k["close"])),
                volume=Decimal(str(k["vol"])),
                close_time=datetime.fromtimestamp(k["id"] + 60, tz=timezone.utc),
            ))
        return klines

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        huobi_symbol = self._to_huobi_symbol(symbol)
        # Huobi depth type: step0/step1/step2/step3/step4/step5
        depth_type = "step0"
        client = await self.get_shared_client()
        resp = await client.get(
            f"{self.BASE_URL}/market/depth",
            params={"symbol": huobi_symbol, "type": depth_type, "depth": str(limit)},
        )
        data = resp.json()
        if data.get("status") != "ok":
            raise ExchangeAPIError("Huobi", data.get("err-msg", "获取订单簿失败"))

        tick = data["tick"]
        return OrderBook(
            bids=[(Decimal(str(p)), Decimal(str(q))) for p, q in tick.get("bids", [])],
            asks=[(Decimal(str(p)), Decimal(str(q))) for p, q in tick.get("asks", [])],
        )

    # ---- 交易接口 ----

    async def get_balance(self) -> list[Balance]:
        """获取现货账户余额"""
        account_id = await self._get_account_id()
        path = f"/v1/account/accounts/{account_id}/balance"
        params = self._sign_params("GET", path)
        client = await self.get_shared_client()
        resp = await client.get(f"{self.BASE_URL}{path}", params=params)
        data = resp.json()
        self._check_huobi_response(data)

        balances = []
        for b in data["data"].get("list", []):
            free = Decimal(str(b.get("balance", "0")))
            locked = Decimal("0")  # Huobi 的 type 字段区分: trade(free) / frozen
            if b.get("type") == "trade":
                balances.append(Balance(
                    asset=b["currency"].upper(),
                    free=free,
                    locked=locked,
                ))
            elif b.get("type") == "frozen":
                # 找到对应的 trade 记录并更新 locked
                for existing in balances:
                    if existing.asset == b["currency"].upper():
                        existing.locked = Decimal(str(b.get("balance", "0")))
                        break
                else:
                    balances.append(Balance(
                        asset=b["currency"].upper(),
                        free=Decimal("0"),
                        locked=Decimal(str(b.get("balance", "0"))),
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
        """
        account_id = await self._get_account_id()
        huobi_symbol = self._to_huobi_symbol(symbol)

        # 构建 order type
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

        params = self._sign_params("POST", path)
        client = await self.get_shared_client()
        resp = await client.post(
            f"{self.BASE_URL}{path}",
            params=params,
            json=body_dict,
        )
        data = resp.json()
        self._check_huobi_response(data)

        return OrderResult(
            exchange_order_id=str(data["data"]),
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
        params = self._sign_params("POST", path)
        client = await self.get_shared_client()
        resp = await client.post(
            f"{self.BASE_URL}{path}",
            params=params,
        )
        data = resp.json()
        self._check_huobi_response(data)
        return str(data["data"]) == order_id

    async def get_order(self, order_id: str, symbol: str) -> OrderResult:
        """查询订单状态"""
        path = f"/v1/order/orders/{order_id}"
        params = self._sign_params("GET", path)
        client = await self.get_shared_client()
        resp = await client.get(f"{self.BASE_URL}{path}", params=params)
        data = resp.json()
        self._check_huobi_response(data)

        o = data["data"]
        filled_qty = Decimal(str(o.get("field-amount", "0")))
        avg_px = Decimal(str(o.get("field-cash-amount", "0")))
        avg_price = (avg_px / filled_qty) if filled_qty > 0 and avg_px > 0 else None

        return OrderResult(
            exchange_order_id=str(o["id"]),
            symbol=o["symbol"].upper(),
            side=o["type"].split("-")[0],
            order_type=o["type"].split("-")[1] if "-" in o["type"] else "market",
            quantity=Decimal(str(o["amount"])),
            price=Decimal(str(o["price"])) if Decimal(str(o.get("price", "0"))) > 0 else None,
            status=_HUOBI_STATUS_MAP.get(o["state"], "pending"),
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
        exchange: 交易所名称 (binance/okx/huobi)
        api_key: API Key（明文）
        secret_key: Secret Key（明文）
        passphrase: OKX 的 passphrase
        testnet: Binance 测试网
        is_demo: OKX 模拟盘

    Returns:
        BaseExchangeAdapter 实例
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
        return BinanceAdapter(api_key, secret_key, passphrase, testnet=testnet)
    elif adapter_class == OKXAdapter:
        return OKXAdapter(api_key, secret_key, passphrase, is_demo=is_demo)
    else:
        return adapter_class(api_key, secret_key, passphrase)
