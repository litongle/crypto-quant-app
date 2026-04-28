"""
OKX 交易所适配器实现
"""
import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone, timedelta
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

_OKX_STATUS_MAP = {
    "live": "pending",
    "partially_filled": "partial",
    "filled": "filled",
    "canceled": "cancelled",
}

class OKXAdapter(BaseExchangeAdapter):
    """OKX 交易所适配器"""

    BASE_URL = "https://www.okx.com"

    RATE_LIMIT_INTERVAL = 0.1

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

    def _to_inst_id(self, symbol: str) -> str:
        stablecoins = ("USDT", "USDC", "BUSD")
        for sc in stablecoins:
            if symbol.endswith(sc):
                base = symbol[: -len(sc)]
                return f"{base}-{sc}"
        return symbol

    def _okx_timestamp(self) -> str:
        adjusted = datetime.now(timezone.utc) + timedelta(milliseconds=self._time_offset_ms)
        return adjusted.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    async def _sync_server_time(self) -> None:
        try:
            client = await self.get_shared_client()
            resp = await client.get(f"{self.BASE_URL}/api/v5/public/time")
            resp.raise_for_status()
            data = resp.json()
            server_ts = int(data["data"][0]["ts"])
            local_ts = int(time.time() * 1000)
            self._time_offset_ms = server_ts - local_ts
            self._time_synced = True
        except Exception as exc:
            logger.warning("[OKXAdapter] 服务器时间同步失败: %s", exc)

    def _sign(self, method: str, path: str, body: str = "") -> dict[str, str]:
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

    async def _ensure_time_synced(self) -> None:
        if not self._time_synced:
            await self._sync_server_time()

    def _check_okx_response(self, data: dict) -> None:
        code = data.get("code", "")
        if code != "0":
            msg = data.get("msg", "Unknown error")
            reject_codes = {"51001", "51002", "51006", "51400", "51503"}
            if code in reject_codes:
                raise OrderRejectedError("OKX", f"[{code}] {msg}", detail_code=code)
            raise ExchangeAPIError("OKX", f"[{code}] {msg}", detail_code=code)

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
                float(_safe_decimal(t.get("ts")) / 1000), tz=timezone.utc
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
                timestamp=datetime.fromtimestamp(float(_safe_decimal(k[0]) / 1000), tz=timezone.utc),
                open=_safe_decimal(k[1]),
                high=_safe_decimal(k[2]),
                low=_safe_decimal(k[3]),
                close=_safe_decimal(k[4]),
                volume=_safe_decimal(k[5]),
                close_time=datetime.fromtimestamp(float(_safe_decimal(k[6]) / 1000), tz=timezone.utc),
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

    async def get_balance(self) -> list[Balance]:
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
            resp = await client.post(f"{self.BASE_URL}{path}", headers=headers, content=body_json)
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, max_attempts=1, context=f"create_order({symbol},{side},{order_type})")
        self._check_okx_response(data)
        order_data = data["data"][0]
        return OrderResult(
            exchange_order_id=order_data.get("ordId", ""),
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
        inst_id = self._to_inst_id(symbol)
        await self._ensure_time_synced()
        path = "/api/v5/trade/cancel-order"
        body_dict = {"instId": inst_id, "ordId": order_id}
        body_json = json.dumps(body_dict)
        async def _do():
            headers = self._sign("POST", path, body_json)
            client = await self.get_shared_client()
            resp = await client.post(f"{self.BASE_URL}{path}", headers=headers, content=body_json)
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, max_attempts=2, context=f"cancel_order({symbol},{order_id})")
        self._check_okx_response(data)
        return data["data"][0].get("sCode") == "0"

    async def get_order(self, order_id: str, symbol: str) -> OrderResult:
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
        return OrderResult(
            exchange_order_id=o.get("ordId", ""),
            symbol=symbol,
            side=o.get("side", "buy").lower(),
            order_type=o.get("ordType", "market").lower(),
            quantity=_safe_decimal(o.get("sz")),
            price=_safe_decimal(o.get("px")) if _safe_decimal(o.get("px")) > 0 else None,
            status=_OKX_STATUS_MAP.get(o.get("state", ""), "pending"),
            filled_quantity=_safe_decimal(o.get("fillSz")),
            avg_fill_price=avg_price if avg_price > 0 else None,
        )

    async def create_stop_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        stop_price: Decimal,
        order_type: str = "stop_loss",
    ) -> OrderResult:
        inst_id = self._to_inst_id(symbol)
        await self._ensure_time_synced()
        path = "/api/v5/trade/order"
        if order_type == "stop_loss":
            body_dict = {
                "instId": inst_id, "tdMode": "cash", "side": side.lower(),
                "ordType": "conditional", "sz": str(quantity), "slTriggerPx": str(stop_price), "slOrdPx": "-1"
            }
        else:
            body_dict = {
                "instId": inst_id, "tdMode": "cash", "side": side.lower(),
                "ordType": "conditional", "sz": str(quantity), "tpTriggerPx": str(stop_price), "tpOrdPx": "-1"
            }
        body_json = json.dumps(body_dict)
        async def _do():
            headers = self._sign("POST", path, body_json)
            client = await self.get_shared_client()
            resp = await client.post(f"{self.BASE_URL}{path}", headers=headers, content=body_json)
            resp.raise_for_status()
            return resp.json()

        data = await self._request_with_retry(_do, max_attempts=1, context=f"create_stop_order({symbol},{order_type})")
        self._check_okx_response(data)
        o = data["data"][0]
        return OrderResult(
            exchange_order_id=o.get("ordId", ""),
            symbol=symbol,
            side=side.lower(),
            order_type=order_type,
            quantity=quantity,
            price=stop_price,
            status="pending",
            filled_quantity=Decimal("0"),
            avg_fill_price=None,
        )
