"""
Huobi (HTX) 交易所适配器实现
"""
import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode
from typing import Any

from app.core.exceptions import (
    ExchangeAPIError,
    OrderRejectedError,
)
from app.core.exchanges.base import (
    BaseExchangeAdapter,
    Ticker,
    Kline,
    OrderBook,
    Balance,
    OrderResult,
    PositionInfo,
    _safe_decimal,
    _safe_divide,
)

logger = logging.getLogger(__name__)

_HUOBI_STATUS_MAP = {
    "submitted": "pending",
    "partial-filled": "partial",
    "filled": "filled",
    "canceled": "cancelled",
    "partial-canceled": "cancelled",
}

class HuobiAdapter(BaseExchangeAdapter):
    """Huobi (HTX) 交易所适配器"""

    BASE_URL = "https://api.huobi.pro"

    RATE_LIMIT_INTERVAL = 0.1

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str | None = None,
    ):
        super().__init__(api_key, secret_key, passphrase)
        self._account_id: str | None = None
        self._account_id_fetched_at: float = 0.0
        self._ACCOUNT_ID_TTL = 300.0

    def _invalidate_account_id_cache(self) -> None:
        self._account_id = None
        self._account_id_fetched_at = 0.0

    def _to_huobi_symbol(self, symbol: str) -> str:
        return symbol.lower()

    def _sign_params(self, method: str, path: str, params: dict | None = None) -> dict:
        params = params or {}
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        sign_params = {
            "AccessKeyId": self.api_key,
            "SignatureMethod": "HmacSHA256",
            "SignatureVersion": "2",
            "Timestamp": timestamp,
            **params,
        }
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
        now = time.monotonic()
        if self._account_id and (now - self._account_id_fetched_at < self._ACCOUNT_ID_TTL):
            return self._account_id

        async def _do():
            path = "/v1/account/accounts"
            params = self._sign_params("GET", path)
            client = await self.get_shared_client()
            resp = await client.get(f"{self.BASE_URL}{path}", params=params)
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context="get_account_id")
        if data.get("status") != "ok":
            err_code = data.get("err-code", "unknown")
            raise ExchangeAPIError("Huobi", data.get("err-msg", "获取账户ID失败"), detail_code=err_code)

        for account in data.get("data", []):
            if account.get("type") == "spot":
                self._account_id = str(account["id"])
                self._account_id_fetched_at = time.monotonic()
                return self._account_id
        if data.get("data"):
            first = data["data"][0]
            self._account_id = str(first["id"])
            self._account_id_fetched_at = time.monotonic()
            return self._account_id
        raise ExchangeAPIError("Huobi", "未找到任何账户")

    def _check_huobi_response(self, data: dict) -> None:
        if data.get("status") != "ok":
            err_msg = data.get("err-msg", "Unknown error")
            err_code = data.get("err-code", "unknown")
            reject_codes = {
                "order-invalid-order-price", "order-invalid-order-amount",
                "insufficient-balance", "invalid-account-id",
                "order-limitorder-amount-min-error",
            }
            if err_code in reject_codes:
                raise OrderRejectedError("Huobi", f"[{err_code}] {err_msg}", detail_code=err_code)
            raise ExchangeAPIError("Huobi", f"[{err_code}] {err_msg}", detail_code=err_code)

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
        open_p = _safe_decimal(tick.get("open"))
        price_change_pct = _safe_divide((close - open_p) * 100, open_p, Decimal("0"))
        return Ticker(
            symbol=symbol, price=close, price_change=close - open_p,
            price_change_percent=price_change_pct or Decimal("0"),
            high_24h=_safe_decimal(tick.get("high")), low_24h=_safe_decimal(tick.get("low")),
            volume_24h=_safe_decimal(tick.get("vol")), quote_volume_24h=_safe_decimal(tick.get("amount")),
            timestamp=datetime.fromtimestamp(float(_safe_decimal(tick.get("version")) / 1000), tz=timezone.utc),
        )

    async def get_klines(self, symbol: str, interval: str, limit: int = 100) -> list[Kline]:
        huobi_symbol = self._to_huobi_symbol(symbol)
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
                timestamp=datetime.fromtimestamp(float(_safe_decimal(k.get("id"))), tz=timezone.utc),
                open=_safe_decimal(k.get("open")), high=_safe_decimal(k.get("high")),
                low=_safe_decimal(k.get("low")), close=_safe_decimal(k.get("close")),
                volume=_safe_decimal(k.get("vol")),
                close_time=datetime.fromtimestamp(float(_safe_decimal(k.get("id")) + 60), tz=timezone.utc),
            ))
        return klines

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        huobi_symbol = self._to_huobi_symbol(symbol)
        async def _do():
            client = await self.get_shared_client()
            resp = await client.get(
                f"{self.BASE_URL}/market/depth",
                params={"symbol": huobi_symbol, "type": "step0", "depth": str(limit)},
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

    async def get_balance(self) -> list[Balance]:
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
            asset = b.get("currency", "").upper()
            val = _safe_decimal(b.get("balance"))
            if b.get("type") == "trade":
                balances.append(Balance(asset=asset, free=val, locked=Decimal("0")))
            elif b.get("type") == "frozen":
                for existing in balances:
                    if existing.asset == asset:
                        existing.locked = val
                        break
                else:
                    balances.append(Balance(asset=asset, free=Decimal("0"), locked=val))
        return [b for b in balances if b.free > 0 or b.locked > 0]

    async def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        return []

    async def create_order(
        self, symbol: str, side: str, order_type: str, quantity: Decimal, price: Decimal | None = None,
    ) -> OrderResult:
        try:
            account_id = await self._get_account_id()
        except ExchangeAPIError:
            self._invalidate_account_id_cache()
            account_id = await self._get_account_id()

        huobi_symbol = self._to_huobi_symbol(symbol)
        huobi_type = f"{side.lower()}-{order_type.lower()}"
        path = "/v1/order/orders/place"
        body = {
            "account-id": account_id, "symbol": huobi_symbol, "type": huobi_type,
            "amount": str(quantity), "source": "spot-api",
        }
        if price and order_type.lower() == "limit":
            body["price"] = str(price)

        async def _do():
            params = self._sign_params("POST", path)
            client = await self.get_shared_client()
            resp = await client.post(f"{self.BASE_URL}{path}", params=params, json=body)
            resp.raise_for_status()
            return resp.json()

        try:
            data = await self._request_with_retry(_do, max_attempts=1, context=f"create_order({symbol})")
        except ExchangeAPIError as exc:
            if exc.detail_code == "invalid-account-id" or "account" in str(exc.message).lower():
                self._invalidate_account_id_cache()
            raise
        self._check_huobi_response(data)
        return OrderResult(
            exchange_order_id=str(data.get("data", "")), symbol=symbol, side=side.lower(),
            order_type=order_type.lower(), quantity=quantity, price=price, status="pending",
            filled_quantity=Decimal("0"), avg_fill_price=None,
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        path = f"/v1/order/orders/{order_id}/submitcancel"
        async def _do():
            params = self._sign_params("POST", path)
            client = await self.get_shared_client()
            resp = await client.post(f"{self.BASE_URL}{path}", params=params)
            resp.raise_for_status()
            return resp.json()
        data = await self._request_with_retry(_do, max_attempts=2, context=f"cancel_order({order_id})")
        self._check_huobi_response(data)
        return str(data.get("data", "")) == order_id

    async def get_order(self, order_id: str, symbol: str) -> OrderResult:
        path = f"/v1/order/orders/{order_id}"
        async def _do():
            params = self._sign_params("GET", path)
            client = await self.get_shared_client()
            resp = await client.get(f"{self.BASE_URL}{path}", params=params)
            resp.raise_for_status()
            return resp.json()
        data = await self._request_with_retry(_do, context=f"get_order({order_id})")
        self._check_huobi_response(data)
        o = data.get("data", {})
        filled = _safe_decimal(o.get("field-amount"))
        cash = _safe_decimal(o.get("field-cash-amount"))
        parts = o.get("type", "buy-market").split("-")
        return OrderResult(
            exchange_order_id=str(o.get("id", "")), symbol=o.get("symbol", symbol).upper(),
            side=parts[0], order_type=parts[1] if len(parts) > 1 else "market",
            quantity=_safe_decimal(o.get("amount")),
            price=_safe_decimal(o.get("price")) if _safe_decimal(o.get("price")) > 0 else None,
            status=_HUOBI_STATUS_MAP.get(o.get("state", ""), "pending"),
            filled_quantity=filled, avg_fill_price=_safe_divide(cash, filled),
        )

    async def create_stop_order(
        self, symbol: str, side: str, quantity: Decimal, stop_price: Decimal, order_type: str = "stop_loss",
    ) -> OrderResult:
        account_id = await self._get_account_id()
        otype = "sell-stop" if side == "sell" else "buy-stop"
        body = {
            "accountId": account_id, "symbol": symbol.lower(), "orderType": "market",
            "type": otype, "amount": str(quantity), "stopPrice": str(stop_price), "source": "api",
        }
        async def _do():
            params = self._sign_params("POST", "/v2/order/algo")
            client = await self.get_shared_client()
            resp = await client.post(f"{self.BASE_URL}/v2/order/algo", params=params, json=body)
            resp.raise_for_status()
            return resp.json()
        data = await self._request_with_retry(_do, max_attempts=1, context=f"create_stop_order({symbol})")
        if data.get("status") != "ok":
            raise OrderRejectedError("huobi", data.get("err-msg", "unknown"))
        return OrderResult(
            exchange_order_id=str(data.get("data", "")), symbol=symbol.upper(), side=side,
            order_type=order_type, quantity=quantity, price=stop_price, status="pending",
            filled_quantity=Decimal("0"), avg_fill_price=None,
        )
