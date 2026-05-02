"""
Huobi (HTX) 交易所适配器实现
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from app.core.exceptions import (
    ExchangeAPIError,
    OrderRejectedError,
)
from app.core.exchanges.base import (
    Balance,
    BaseExchangeAdapter,
    Kline,
    OrderBook,
    OrderResult,
    PositionInfo,
    SymbolInfo,
    Ticker,
    _format_decimal,
    _precision_to_step,
    _quantize_to_step,
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
    FUTURES_URL = "https://api.hbdm.com"

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
        self._ACCOUNT_ID_TTL = 60.0
        self._account_id_lock = asyncio.Lock()

    def _invalidate_account_id_cache(self) -> None:
        self._account_id = None
        self._account_id_fetched_at = 0.0

    def _to_huobi_symbol(self, symbol: str) -> str:
        return symbol.lower()

    @staticmethod
    def _to_perp_contract_code(symbol: str) -> str:
        upper_symbol = symbol.upper()
        for stablecoin in ("USDT", "USDC"):
            if upper_symbol.endswith(stablecoin):
                return f"{upper_symbol[: -len(stablecoin)]}-{stablecoin}"
        return upper_symbol

    @staticmethod
    def _symbol_from_contract_code(contract_code: str) -> str:
        return contract_code.replace("-", "").upper()

    def _sign_params(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        *,
        base_url: str | None = None,
    ) -> dict:
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
        host = (base_url or self.BASE_URL).replace("https://", "").replace("http://", "")
        payload = f"{method.upper()}\n{host}\n{path}\n{query_string}"
        signature = base64.b64encode(
            hmac.new(self.secret_key.encode(), payload.encode(), hashlib.sha256).digest()
        ).decode()
        sign_params["Signature"] = signature
        return sign_params

    def _prepare_quantity(self, quantity: Decimal, info: SymbolInfo) -> Decimal:
        normalized = _quantize_to_step(quantity, info.step_size)
        if normalized <= 0 or (info.min_qty > 0 and normalized < info.min_qty):
            raise OrderRejectedError("Huobi", f"下单数量 {quantity} 小于交易所最小要求")
        return normalized

    def _prepare_price(self, price: Decimal, info: SymbolInfo) -> Decimal:
        normalized = _quantize_to_step(price, info.tick_size)
        if normalized <= 0:
            raise OrderRejectedError("Huobi", f"价格 {price} 无效")
        return normalized

    async def _get_account_id(self) -> str:
        now = time.monotonic()
        if self._account_id and (now - self._account_id_fetched_at < self._ACCOUNT_ID_TTL):
            return self._account_id
        async with self._account_id_lock:
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
                raise ExchangeAPIError(
                    "Huobi", data.get("err-msg", "获取账户ID失败"), detail_code=err_code
                )

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
                "order-invalid-order-price",
                "order-invalid-order-amount",
                "insufficient-balance",
                "invalid-account-id",
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
            symbol=symbol,
            price=close,
            price_change=close - open_p,
            price_change_percent=price_change_pct or Decimal("0"),
            high_24h=_safe_decimal(tick.get("high")),
            low_24h=_safe_decimal(tick.get("low")),
            volume_24h=_safe_decimal(tick.get("vol")),
            quote_volume_24h=_safe_decimal(tick.get("amount")),
            timestamp=datetime.fromtimestamp(float(_safe_decimal(data.get("ts")) / 1000), tz=UTC),
        )

    async def get_klines(self, symbol: str, interval: str, limit: int = 100) -> list[Kline]:
        huobi_symbol = self._to_huobi_symbol(symbol)
        period_map = {
            "1m": "1min",
            "5m": "5min",
            "15m": "15min",
            "30m": "30min",
            "1h": "60min",
            "4h": "4hour",
            "1d": "1day",
            "1w": "1week",
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
            klines.append(
                Kline(
                    timestamp=datetime.fromtimestamp(float(_safe_decimal(k.get("id"))), tz=UTC),
                    open=_safe_decimal(k.get("open")),
                    high=_safe_decimal(k.get("high")),
                    low=_safe_decimal(k.get("low")),
                    close=_safe_decimal(k.get("close")),
                    volume=_safe_decimal(k.get("vol")),
                    close_time=datetime.fromtimestamp(
                        float(_safe_decimal(k.get("id")) + 60), tz=UTC
                    ),
                )
            )
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
        contract_code = self._to_perp_contract_code(symbol) if symbol else None

        async def _fetch_positions(path: str) -> list[dict[str, Any]]:
            payload: dict[str, Any] = {}
            if contract_code:
                payload["contract_code"] = contract_code

            async def _do():
                params = self._sign_params(
                    "POST",
                    path,
                    base_url=self.FUTURES_URL,
                )
                client = await self.get_shared_client()
                resp = await client.post(
                    f"{self.FUTURES_URL}{path}",
                    params=params,
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()

            data = await self._request_with_retry(_do, context=f"get_positions({path})")
            self._check_huobi_response(data)
            return data.get("data", [])

        position_rows = await _fetch_positions("/linear-swap-api/v1/swap_position_info")
        position_rows.extend(await _fetch_positions("/linear-swap-api/v1/swap_cross_position_info"))

        positions = []
        for item in position_rows:
            volume = _safe_decimal(item.get("volume"))
            if volume <= 0:
                continue
            direction = item.get("direction", "buy").lower()
            side = "long" if direction == "buy" else "short"
            positions.append(
                PositionInfo(
                    symbol=self._symbol_from_contract_code(item.get("contract_code", "")),
                    side=side,
                    quantity=volume,
                    entry_price=_safe_decimal(item.get("cost_open")),
                    current_price=_safe_decimal(item.get("last_price")),
                    unrealized_pnl=_safe_decimal(item.get("profit_unreal")),
                    leverage=int(_safe_decimal(item.get("lever_rate"), Decimal("1"))),
                )
            )
        return positions

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
    ) -> OrderResult:
        info = await self.get_exchange_info(symbol)
        normalized_quantity = self._prepare_quantity(quantity, info)
        try:
            account_id = await self._get_account_id()
        except ExchangeAPIError:
            self._invalidate_account_id_cache()
            account_id = await self._get_account_id()

        huobi_symbol = self._to_huobi_symbol(symbol)
        huobi_type = f"{side.lower()}-{order_type.lower()}"
        path = "/v1/order/orders/place"
        body = {
            "account-id": account_id,
            "symbol": huobi_symbol,
            "type": huobi_type,
            "amount": _format_decimal(normalized_quantity),
            "source": "spot-api",
        }
        if price and order_type.lower() == "limit":
            body["price"] = _format_decimal(self._prepare_price(price, info))

        async def _do():
            params = self._sign_params("POST", path)
            client = await self.get_shared_client()
            resp = await client.post(f"{self.BASE_URL}{path}", params=params, json=body)
            resp.raise_for_status()
            return resp.json()

        try:
            data = await self._request_with_retry(
                _do, max_attempts=1, context=f"create_order({symbol})"
            )
        except ExchangeAPIError as exc:
            if exc.detail_code == "invalid-account-id" or "account" in str(exc.message).lower():
                self._invalidate_account_id_cache()
            raise
        self._check_huobi_response(data)
        return OrderResult(
            exchange_order_id=str(data.get("data", "")),
            symbol=symbol,
            side=side.lower(),
            order_type=order_type.lower(),
            quantity=normalized_quantity,
            price=price,
            status="pending",
            filled_quantity=Decimal("0"),
            avg_fill_price=None,
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        path = f"/v1/order/orders/{order_id}/submitcancel"

        async def _do():
            params = self._sign_params("POST", path)
            client = await self.get_shared_client()
            resp = await client.post(f"{self.BASE_URL}{path}", params=params)
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(
            _do, max_attempts=2, context=f"cancel_order({order_id})"
        )
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
            exchange_order_id=str(o.get("id", "")),
            symbol=o.get("symbol", symbol).upper(),
            side=parts[0],
            order_type=parts[1] if len(parts) > 1 else "market",
            quantity=_safe_decimal(o.get("amount")),
            price=_safe_decimal(o.get("price")) if _safe_decimal(o.get("price")) > 0 else None,
            status=_HUOBI_STATUS_MAP.get(o.get("state", ""), "pending"),
            filled_quantity=filled,
            avg_fill_price=_safe_divide(cash, filled),
        )

    async def create_stop_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        stop_price: Decimal,
        order_type: str = "stop_loss",
    ) -> OrderResult:
        contract_code = self._to_perp_contract_code(symbol)
        trigger_price = _format_decimal(stop_price)
        trigger_direction = "le" if side.lower() == "sell" else "ge"
        if order_type == "take_profit":
            trigger_direction = "ge" if side.lower() == "sell" else "le"
        body = {
            "contract_code": contract_code,
            "direction": side.lower(),
            "offset": "close",
            "volume": _format_decimal(quantity),
            "trigger_type": "ge" if trigger_direction == "ge" else "le",
            "trigger_price": trigger_price,
            "order_price_type": "optimal_20",
        }

        async def _do():
            path = "/linear-swap-api/v1/swap_trigger_order"
            params = self._sign_params("POST", path, base_url=self.FUTURES_URL)
            client = await self.get_shared_client()
            resp = await client.post(f"{self.FUTURES_URL}{path}", params=params, json=body)
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(
            _do, max_attempts=1, context=f"create_stop_order({symbol})"
        )
        self._check_huobi_response(data)
        order_data = data.get("data", {})
        return OrderResult(
            exchange_order_id=str(order_data.get("order_id", order_data.get("order-id", ""))),
            symbol=symbol.upper(),
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=stop_price,
            status="pending",
            filled_quantity=Decimal("0"),
            avg_fill_price=None,
        )

    async def get_exchange_info(self, symbol: str) -> SymbolInfo:
        """获取交易对精度信息（评审问题2：Huobi API）"""
        symbol_lower = symbol.lower()

        async def _do():
            client = await self.get_shared_client()
            resp = await client.get(f"{self.BASE_URL}/v2/settings/common/symbols")
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_exchange_info({symbol})")
        if data.get("status") != "ok":
            raise ExchangeAPIError("Huobi", "获取交易对信息失败")

        for s in data.get("data", []):
            if s.get("sc").lower() == symbol_lower:
                amount_step = _precision_to_step(
                    s.get("ap")
                    or s.get("amount-precision")
                    or s.get("tap")
                    or s.get("toa")
                )
                price_step = _precision_to_step(
                    s.get("pp")
                    or s.get("price-precision")
                    or s.get("tpp")
                    or s.get("tp")
                )
                return SymbolInfo(
                    symbol=symbol.upper(),
                    min_qty=_safe_decimal(s.get("minoa")),
                    step_size=amount_step,
                    min_notional=_safe_decimal(s.get("minov")),
                    tick_size=price_step,
                )
        raise ExchangeAPIError("Huobi", f"交易对 {symbol} 不存在")
