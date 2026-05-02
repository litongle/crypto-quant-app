"""
Binance 交易所适配器实现
"""

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
    _quantize_to_step,
    _safe_decimal,
    _safe_divide,
)

logger = logging.getLogger(__name__)

_BINANCE_STATUS_MAP = {
    "NEW": "pending",
    "PARTIALLY_FILLED": "partial",
    "FILLED": "filled",
    "CANCELED": "cancelled",
    "EXPIRED": "cancelled",
    "REJECTED": "rejected",
    "PENDING_CANCEL": "pending",
}


class BinanceAdapter(BaseExchangeAdapter):
    """Binance 交易所适配器"""

    BASE_URL = "https://api.binance.com"
    TESTNET_URL = "https://testnet.binance.vision"
    FAPI_URL = "https://fapi.binance.com"
    FAPI_TESTNET_URL = "https://testnet.binancefuture.com"

    RATE_LIMIT_INTERVAL_SPOT = 0.1
    RATE_LIMIT_INTERVAL_FUTURES = 0.05

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str | None = None,
        testnet: bool = False,
        is_futures: bool = False,
    ):
        super().__init__(api_key, secret_key, passphrase)
        self.is_futures = is_futures
        if is_futures:
            self.base_url = self.FAPI_TESTNET_URL if testnet else self.FAPI_URL
            self.RATE_LIMIT_INTERVAL = self.RATE_LIMIT_INTERVAL_FUTURES
        else:
            self.base_url = self.TESTNET_URL if testnet else self.BASE_URL
            self.RATE_LIMIT_INTERVAL = self.RATE_LIMIT_INTERVAL_SPOT
        self.testnet = testnet

    def _sign_params(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(params)
        signature = hmac.new(
            self.secret_key.encode(), query_string.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _auth_headers(self) -> dict[str, str]:
        return {"X-MBX-APIKEY": self.api_key}

    def _prepare_quantity(self, quantity: Decimal, info: SymbolInfo) -> Decimal:
        normalized = _quantize_to_step(quantity, info.step_size)
        if normalized <= 0 or (info.min_qty > 0 and normalized < info.min_qty):
            raise OrderRejectedError(
                "Binance",
                f"下单数量 {quantity} 小于最小步进/最小数量要求",
            )
        return normalized

    def _prepare_price(self, price: Decimal, info: SymbolInfo) -> Decimal:
        normalized = _quantize_to_step(price, info.tick_size)
        if normalized <= 0:
            raise OrderRejectedError("Binance", f"价格 {price} 无效")
        return normalized

    def _check_response(self, data: dict, exchange: str = "Binance") -> None:
        if "code" in data and data["code"] != 200:
            msg = data.get("msg", "Unknown error")
            code = str(data.get("code", ""))
            reject_codes = {"-2010", "-1013", "-2015"}
            if code in reject_codes:
                raise OrderRejectedError(exchange, f"[{code}] {msg}", detail_code=code)
            raise ExchangeAPIError(exchange=exchange, message=f"[{code}] {msg}", detail_code=code)

    async def get_ticker(self, symbol: str) -> Ticker:
        normalized_symbol = symbol.upper()

        async def _do():
            client = await self.get_shared_client()
            resp = await client.get(
                f"{self.base_url}/api/v3/ticker/24hr",
                params={"symbol": normalized_symbol},
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_ticker({normalized_symbol})")
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
                float(_safe_decimal(data.get("closeTime"), Decimal("0")) / 1000),
                tz=UTC,
            ),
        )

    async def get_klines(self, symbol: str, interval: str, limit: int = 100) -> list[Kline]:
        normalized_symbol = symbol.upper()

        async def _do():
            client = await self.get_shared_client()
            resp = await client.get(
                f"{self.base_url}/api/v3/klines",
                params={"symbol": normalized_symbol, "interval": interval, "limit": limit},
            )
            resp.raise_for_status()
            return resp.json()

        raw = await self._request_with_retry(_do, context=f"get_klines({normalized_symbol})")
        klines = []
        for k in raw:
            klines.append(
                Kline(
                    timestamp=datetime.fromtimestamp(float(_safe_decimal(k[0]) / 1000), tz=UTC),
                    open=_safe_decimal(k[1]),
                    high=_safe_decimal(k[2]),
                    low=_safe_decimal(k[3]),
                    close=_safe_decimal(k[4]),
                    volume=_safe_decimal(k[5]),
                    close_time=datetime.fromtimestamp(float(_safe_decimal(k[6]) / 1000), tz=UTC),
                )
            )
        return klines

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        normalized_symbol = symbol.upper()

        async def _do():
            client = await self.get_shared_client()
            resp = await client.get(
                f"{self.base_url}/api/v3/depth",
                params={"symbol": normalized_symbol, "limit": limit},
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_orderbook({normalized_symbol})")
        return OrderBook(
            bids=[(_safe_decimal(p), _safe_decimal(q)) for p, q in data.get("bids", [])],
            asks=[(_safe_decimal(p), _safe_decimal(q)) for p, q in data.get("asks", [])],
        )

    async def get_balance(self) -> list[Balance]:
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
                balances.append(
                    Balance(
                        asset=b.get("asset", ""),
                        free=free,
                        locked=locked,
                    )
                )
        return balances

    async def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        if not self.is_futures:
            return []

        normalized_symbol = symbol.upper() if symbol else None

        async def _do():
            client = await self.get_shared_client()
            params: dict[str, Any] = {}
            if normalized_symbol:
                params["symbol"] = normalized_symbol
            resp = await client.get(
                f"{self.base_url}/fapi/v2/positionRisk",
                params=self._sign_params(params),
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_positions({normalized_symbol})")
        positions = []
        for item in data:
            quantity = _safe_decimal(item.get("positionAmt"))
            if quantity == 0:
                continue
            side = "long" if quantity > 0 else "short"
            positions.append(
                PositionInfo(
                    symbol=item.get("symbol", ""),
                    side=side,
                    quantity=abs(quantity),
                    entry_price=_safe_decimal(item.get("entryPrice")),
                    current_price=_safe_decimal(item.get("markPrice")),
                    unrealized_pnl=_safe_decimal(item.get("unRealizedProfit")),
                    leverage=int(_safe_decimal(item.get("leverage"), Decimal("1"))),
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

        async def _do():
            client = await self.get_shared_client()
            params: dict[str, Any] = {
                "symbol": symbol.upper(),
                "side": side.upper(),
                "type": order_type.upper(),
                "quantity": _format_decimal(normalized_quantity),
            }
            if order_type.lower() == "limit":
                if price is None:
                    raise OrderRejectedError("Binance", "限价单必须指定价格")
                normalized_price = self._prepare_price(price, info)
                params["price"] = _format_decimal(normalized_price)
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
            _do,
            max_attempts=1,
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
            quantity=_safe_decimal(data.get("origQty"), normalized_quantity),
            price=_safe_decimal(data.get("price"))
            if _safe_decimal(data.get("price")) > 0
            else None,
            status=_BINANCE_STATUS_MAP.get(data.get("status", ""), "pending"),
            filled_quantity=executed_qty,
            avg_fill_price=_safe_divide(cumm_quote, executed_qty),
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        async def _do():
            client = await self.get_shared_client()
            params = self._sign_params(
                {
                    "symbol": symbol.upper(),
                    "orderId": order_id,
                }
            )
            resp = await client.delete(
                f"{self.base_url}/api/v3/order",
                params=params,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(
            _do,
            max_attempts=2,
            context=f"cancel_order({symbol},{order_id})",
        )
        self._check_response(data)
        return data.get("status") in ("CANCELED", "CANCELLED")

    async def get_order(self, order_id: str, symbol: str) -> OrderResult:
        async def _do():
            client = await self.get_shared_client()
            params = self._sign_params(
                {
                    "symbol": symbol.upper(),
                    "orderId": order_id,
                }
            )
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
            side=data.get("side", "buy").lower(),
            order_type=data.get("type", "market").lower(),
            quantity=_safe_decimal(data.get("origQty")),
            price=_safe_decimal(data.get("price"))
            if _safe_decimal(data.get("price")) > 0
            else None,
            status=_BINANCE_STATUS_MAP.get(data.get("status", ""), "pending"),
            filled_quantity=executed_qty,
            avg_fill_price=_safe_divide(cumm_quote, executed_qty),
        )

    async def create_stop_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        stop_price: Decimal,
        order_type: str = "stop_loss",
    ) -> OrderResult:
        binance_type = "STOP_LOSS" if order_type == "stop_loss" else "TAKE_PROFIT"
        info = await self.get_exchange_info(symbol)
        normalized_quantity = self._prepare_quantity(quantity, info)
        normalized_stop_price = self._prepare_price(stop_price, info)

        async def _do():
            client = await self.get_shared_client()
            params: dict[str, Any] = {
                "symbol": symbol.upper(),
                "side": side.upper(),
                "type": binance_type,
                "quantity": _format_decimal(normalized_quantity),
                "stopPrice": _format_decimal(normalized_stop_price),
            }
            params = self._sign_params(params)
            resp = await client.post(
                f"{self.base_url}/api/v3/order",
                params=params,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(
            _do,
            max_attempts=1,
            context=f"create_stop_order({symbol},{side},{binance_type},stop={stop_price})",
        )
        self._check_response(data)

        executed_qty = _safe_decimal(data.get("executedQty"))
        cumm_quote = _safe_decimal(data.get("cummulativeQuoteQty"))

        return OrderResult(
            exchange_order_id=str(data.get("orderId", "")),
            symbol=data.get("symbol", symbol),
            side=data.get("side", side).lower(),
            order_type=order_type,
            quantity=_safe_decimal(data.get("origQty"), normalized_quantity),
            price=_safe_decimal(data.get("stopPrice", normalized_stop_price)),
            status=_BINANCE_STATUS_MAP.get(data.get("status", ""), "pending"),
            filled_quantity=executed_qty,
            avg_fill_price=_safe_divide(cumm_quote, executed_qty),
        )

    async def get_exchange_info(self, symbol: str) -> SymbolInfo:
        """获取交易对精度信息（评审问题2：从交易所 API 动态获取 min_qty/step_size）"""
        endpoint = "/fapi/v1/exchangeInfo" if self.is_futures else "/api/v3/exchangeInfo"

        async def _do():
            client = await self.get_shared_client()
            resp = await client.get(
                f"{self.base_url}{endpoint}",
                params={"symbol": symbol.upper()},
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, context=f"get_exchange_info({symbol})")
        symbols = data.get("symbols", [])
        if not symbols:
            raise ExchangeAPIError("Binance", f"交易对 {symbol} 不存在")

        s = symbols[0]
        min_qty = Decimal("0")
        step_size = Decimal("0")
        min_notional = Decimal("0")
        tick_size = Decimal("0")

        for f in s.get("filters", []):
            ft = f.get("filterType", "")
            if ft == "LOT_SIZE":
                min_qty = _safe_decimal(f.get("minQty"))
                step_size = _safe_decimal(f.get("stepSize"))
            elif ft == "MIN_NOTIONAL" or ft == "NOTIONAL":
                min_notional = _safe_decimal(f.get("minNotional"))
            elif ft == "PRICE_FILTER":
                tick_size = _safe_decimal(f.get("tickSize"))

        return SymbolInfo(
            symbol=symbol.upper(),
            min_qty=min_qty,
            step_size=step_size,
            min_notional=min_notional,
            tick_size=tick_size,
        )
