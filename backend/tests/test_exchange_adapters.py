"""
交易所适配器测试 — 因子函数、状态映射、响应解析、错误分类

通过 mock httpx 客户端，避免真实网络请求。
"""
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.core.exceptions import (
    ExchangeAPIError,
    NetworkError,
    OrderRejectedError,
    RateLimitError,
)
from app.core.exchange_adapter import get_exchange_adapter
from app.core.exchanges import BinanceAdapter, HuobiAdapter, OKXAdapter
from app.core.exchanges.base import (
    BaseExchangeAdapter,
    _safe_decimal,
    _safe_divide,
)


# ==================== Helpers ====================

def _fake_response(json_body: dict | list, status_code: int = 200) -> MagicMock:
    """构造一个仿造 httpx.Response 的 mock 对象"""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    if status_code >= 400:
        request = httpx.Request("GET", "http://test")
        real = httpx.Response(status_code, request=request, content=json.dumps(json_body))
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=request, response=real
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def _patch_client(
    monkeypatch,
    *,
    get_response=None,
    post_response=None,
    delete_response=None,
):
    """替换 BaseExchangeAdapter.get_shared_client 返回 mock client"""
    client = MagicMock()
    client.get = AsyncMock(return_value=get_response)
    client.post = AsyncMock(return_value=post_response)
    client.delete = AsyncMock(return_value=delete_response)
    client.is_closed = False

    async def _get_shared_client():
        return client

    monkeypatch.setattr(
        BaseExchangeAdapter, "get_shared_client",
        classmethod(lambda cls: _get_shared_client()),
    )
    return client


# ==================== Factory ====================

class TestGetExchangeAdapter:
    def test_factory_returns_binance(self):
        adapter = get_exchange_adapter(
            "binance", api_key="k", secret_key="s",
        )
        assert isinstance(adapter, BinanceAdapter)
        assert adapter.testnet is False

    def test_factory_returns_binance_testnet(self):
        adapter = get_exchange_adapter(
            "binance", api_key="k", secret_key="s", testnet=True,
        )
        assert isinstance(adapter, BinanceAdapter)
        assert adapter.testnet is True
        assert "testnet" in adapter.base_url

    def test_factory_returns_okx(self):
        adapter = get_exchange_adapter(
            "okx", api_key="k", secret_key="s", passphrase="p",
        )
        assert isinstance(adapter, OKXAdapter)

    def test_factory_returns_huobi(self):
        adapter = get_exchange_adapter(
            "huobi", api_key="k", secret_key="s",
        )
        assert isinstance(adapter, HuobiAdapter)

    def test_factory_accepts_htx_alias(self):
        adapter = get_exchange_adapter(
            "htx", api_key="k", secret_key="s",
        )
        assert isinstance(adapter, HuobiAdapter)

    def test_factory_case_insensitive(self):
        adapter = get_exchange_adapter(
            "BINANCE", api_key="k", secret_key="s",
        )
        assert isinstance(adapter, BinanceAdapter)

    def test_factory_unknown_exchange_raises(self):
        with pytest.raises(ValueError, match="不支持"):
            get_exchange_adapter("kraken", api_key="k", secret_key="s")


# ==================== Safe helpers ====================

class TestSafeHelpers:
    def test_safe_decimal_handles_none(self):
        assert _safe_decimal(None) == Decimal("0")

    def test_safe_decimal_handles_invalid_string(self):
        assert _safe_decimal("abc") == Decimal("0")

    def test_safe_decimal_handles_empty_string(self):
        assert _safe_decimal("") == Decimal("0")
        assert _safe_decimal("   ") == Decimal("0")

    def test_safe_decimal_custom_default(self):
        assert _safe_decimal(None, default=Decimal("99")) == Decimal("99")

    def test_safe_decimal_valid_value(self):
        assert _safe_decimal("3.14") == Decimal("3.14")
        assert _safe_decimal(42) == Decimal("42")

    def test_safe_divide_zero_denominator(self):
        assert _safe_divide(Decimal("10"), Decimal("0")) is None

    def test_safe_divide_with_default(self):
        assert _safe_divide(
            Decimal("10"), Decimal("0"), default=Decimal("0")
        ) == Decimal("0")

    def test_safe_divide_normal(self):
        assert _safe_divide(Decimal("10"), Decimal("2")) == Decimal("5")


# ==================== Error classification ====================

class TestErrorClassification:
    def test_timeout_classified_as_network_error(self):
        err = BaseExchangeAdapter._classify_error(
            httpx.TimeoutException("read timeout"), "Binance"
        )
        assert isinstance(err, NetworkError)
        assert err.retryable is True

    def test_connect_error_classified_as_network_error(self):
        err = BaseExchangeAdapter._classify_error(
            httpx.ConnectError("connection refused"), "Binance"
        )
        assert isinstance(err, NetworkError)
        assert err.retryable is True

    def test_429_classified_as_rate_limit(self):
        request = httpx.Request("GET", "http://test")
        response = httpx.Response(429, request=request)
        exc = httpx.HTTPStatusError("rate", request=request, response=response)
        err = BaseExchangeAdapter._classify_error(exc, "Binance")
        assert isinstance(err, RateLimitError)
        assert err.retryable is True

    def test_400_classified_as_order_rejected(self):
        request = httpx.Request("POST", "http://test")
        response = httpx.Response(
            400, request=request,
            content=json.dumps({"code": -1013, "msg": "Filter failure"}),
        )
        exc = httpx.HTTPStatusError("400", request=request, response=response)
        err = BaseExchangeAdapter._classify_error(exc, "Binance")
        assert isinstance(err, OrderRejectedError)
        assert err.retryable is False
        assert err.detail_code == -1013

    def test_401_classified_as_order_rejected(self):
        request = httpx.Request("POST", "http://test")
        response = httpx.Response(
            401, request=request,
            content=json.dumps({"msg": "Invalid signature"}),
        )
        exc = httpx.HTTPStatusError("401", request=request, response=response)
        err = BaseExchangeAdapter._classify_error(exc, "Binance")
        assert isinstance(err, OrderRejectedError)

    def test_500_classified_as_network_retryable(self):
        request = httpx.Request("POST", "http://test")
        response = httpx.Response(500, request=request)
        exc = httpx.HTTPStatusError("500", request=request, response=response)
        err = BaseExchangeAdapter._classify_error(exc, "Binance")
        assert isinstance(err, NetworkError)
        assert err.retryable is True

    def test_passes_through_existing_exchange_error(self):
        original = OrderRejectedError("Binance", "rejected")
        err = BaseExchangeAdapter._classify_error(original, "Binance")
        assert err is original

    def test_unknown_exception_classified_as_generic(self):
        err = BaseExchangeAdapter._classify_error(
            RuntimeError("oops"), "Binance"
        )
        assert isinstance(err, ExchangeAPIError)
        assert err.retryable is False


# ==================== Binance: response parsing ====================

class TestBinanceAdapter:
    def setup_method(self):
        self.adapter = BinanceAdapter(
            api_key="test_key",
            secret_key="test_secret_xxxxxxxxxxxx",
        )

    def test_check_response_no_error_for_normal_payload(self):
        # 没有 error code 字段时不应抛错
        self.adapter._check_response({"symbol": "BTCUSDT", "price": "50000"})

    def test_check_response_raises_order_rejected_for_2010(self):
        # -2010 是 Binance 的 INSUFFICIENT_BALANCE 类错误
        with pytest.raises(OrderRejectedError) as exc_info:
            self.adapter._check_response(
                {"code": -2010, "msg": "Account has insufficient balance"}
            )
        assert exc_info.value.detail_code == "-2010"

    def test_check_response_raises_order_rejected_for_1013(self):
        with pytest.raises(OrderRejectedError):
            self.adapter._check_response(
                {"code": -1013, "msg": "Filter failure"}
            )

    def test_check_response_raises_generic_for_other_codes(self):
        with pytest.raises(ExchangeAPIError) as exc_info:
            self.adapter._check_response(
                {"code": -1000, "msg": "Unknown error"}
            )
        # 不应当是 OrderRejected
        assert not isinstance(exc_info.value, OrderRejectedError)

    def test_sign_params_adds_signature(self):
        signed = self.adapter._sign_params({"symbol": "BTCUSDT"})
        assert "signature" in signed
        assert "timestamp" in signed
        assert isinstance(signed["signature"], str)
        assert len(signed["signature"]) == 64  # HMAC-SHA256 hex 长度

    def test_auth_headers_includes_api_key(self):
        headers = self.adapter._auth_headers()
        assert headers["X-MBX-APIKEY"] == "test_key"

    async def test_get_ticker_parses_response(self, monkeypatch):
        ticker_payload = {
            "symbol": "BTCUSDT",
            "lastPrice": "50000.00",
            "priceChange": "1000.00",
            "priceChangePercent": "2.04",
            "highPrice": "51000.00",
            "lowPrice": "49000.00",
            "volume": "1234.56",
            "quoteVolume": "61728000.00",
            "closeTime": 1700000000000,
        }
        _patch_client(monkeypatch, get_response=_fake_response(ticker_payload))

        ticker = await self.adapter.get_ticker("BTCUSDT")
        assert ticker.symbol == "BTCUSDT"
        assert ticker.price == Decimal("50000.00")
        assert ticker.high_24h == Decimal("51000.00")
        assert ticker.low_24h == Decimal("49000.00")

    async def test_get_klines_parses_array(self, monkeypatch):
        klines_payload = [
            [1700000000000, "50000", "51000", "49500", "50500", "100",
             1700003600000, "5050000", 100, "60", "3030000", "0"],
            [1700003600000, "50500", "51500", "50000", "51000", "120",
             1700007200000, "6120000", 120, "70", "3570000", "0"],
        ]
        _patch_client(monkeypatch, get_response=_fake_response(klines_payload))

        klines = await self.adapter.get_klines("BTCUSDT", "1h", limit=2)
        assert len(klines) == 2
        assert klines[0].open == Decimal("50000")
        assert klines[0].close == Decimal("50500")
        assert klines[1].high == Decimal("51500")

    async def test_get_orderbook_parses_bids_asks(self, monkeypatch):
        orderbook_payload = {
            "bids": [["50000", "0.5"], ["49999", "1.2"]],
            "asks": [["50001", "0.3"], ["50002", "0.8"]],
        }
        _patch_client(monkeypatch, get_response=_fake_response(orderbook_payload))

        ob = await self.adapter.get_orderbook("BTCUSDT")
        assert len(ob.bids) == 2
        assert len(ob.asks) == 2
        assert ob.bids[0] == (Decimal("50000"), Decimal("0.5"))
        assert ob.asks[0] == (Decimal("50001"), Decimal("0.3"))

    async def test_create_order_parses_filled_response(self, monkeypatch):
        order_payload = {
            "orderId": 123456,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "MARKET",
            "origQty": "0.01",
            "executedQty": "0.01",
            "cummulativeQuoteQty": "500.00",
            "status": "FILLED",
            "price": "0.00",
        }
        _patch_client(monkeypatch, post_response=_fake_response(order_payload))

        result = await self.adapter.create_order(
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=Decimal("0.01"),
        )
        assert result.exchange_order_id == "123456"
        assert result.status == "filled"
        assert result.filled_quantity == Decimal("0.01")
        # 平均价 = 500 / 0.01 = 50000
        assert result.avg_fill_price == Decimal("50000")

    async def test_create_order_maps_partial_status(self, monkeypatch):
        order_payload = {
            "orderId": 1,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "origQty": "1",
            "executedQty": "0.5",
            "cummulativeQuoteQty": "25000",
            "status": "PARTIALLY_FILLED",
            "price": "50000",
        }
        _patch_client(monkeypatch, post_response=_fake_response(order_payload))

        result = await self.adapter.create_order(
            symbol="BTCUSDT", side="buy", order_type="limit",
            quantity=Decimal("1"), price=Decimal("50000"),
        )
        assert result.status == "partial"
        assert result.filled_quantity == Decimal("0.5")

    async def test_create_limit_order_without_price_raises(self):
        # 没 mock client 也能拦截，因为参数校验在 _do 内
        with pytest.raises(OrderRejectedError):
            await self.adapter.create_order(
                symbol="BTCUSDT", side="buy", order_type="limit",
                quantity=Decimal("1"),
            )

    async def test_cancel_order_returns_true_on_canceled(self, monkeypatch):
        cancel_payload = {"orderId": 1, "status": "CANCELED"}
        _patch_client(
            monkeypatch, delete_response=_fake_response(cancel_payload)
        )
        result = await self.adapter.cancel_order("1", "BTCUSDT")
        assert result is True

    async def test_cancel_order_returns_false_on_other_status(self, monkeypatch):
        cancel_payload = {"orderId": 1, "status": "FILLED"}
        _patch_client(
            monkeypatch, delete_response=_fake_response(cancel_payload)
        )
        result = await self.adapter.cancel_order("1", "BTCUSDT")
        assert result is False

    async def test_get_balance_filters_zero_balances(self, monkeypatch):
        balance_payload = {
            "balances": [
                {"asset": "BTC", "free": "0.5", "locked": "0"},
                {"asset": "ETH", "free": "0", "locked": "0"},  # 应当被过滤
                {"asset": "USDT", "free": "0", "locked": "100"},  # locked > 0 保留
            ]
        }
        _patch_client(monkeypatch, get_response=_fake_response(balance_payload))

        balances = await self.adapter.get_balance()
        assets = {b.asset for b in balances}
        assert "BTC" in assets
        assert "USDT" in assets
        assert "ETH" not in assets


# ==================== Binance status mapping ====================

class TestBinanceStatusMapping:
    """确保所有 Binance 订单状态都映射到内部状态"""

    def setup_method(self):
        from app.core.exchanges.binance import _BINANCE_STATUS_MAP
        self.mapping = _BINANCE_STATUS_MAP

    def test_new_to_pending(self):
        assert self.mapping["NEW"] == "pending"

    def test_filled_stays_filled(self):
        assert self.mapping["FILLED"] == "filled"

    def test_partially_filled_to_partial(self):
        assert self.mapping["PARTIALLY_FILLED"] == "partial"

    def test_canceled_to_cancelled(self):
        # 注意拼写：交易所返回 CANCELED，内部统一 cancelled
        assert self.mapping["CANCELED"] == "cancelled"

    def test_expired_to_cancelled(self):
        assert self.mapping["EXPIRED"] == "cancelled"

    def test_rejected_stays_rejected(self):
        assert self.mapping["REJECTED"] == "rejected"
