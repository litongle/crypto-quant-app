"""
订单 / 账户 API 集成测试 — 鉴权、IDOR、数据校验
"""
import pytest
from httpx import AsyncClient


# ==================== 账户管理 ====================

class TestAccountsAPI:
    async def test_get_accounts_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/trading/accounts")
        assert resp.status_code in (401, 403)

    async def test_get_accounts_returns_empty_when_no_accounts(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.get(
            "/api/v1/trading/accounts", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    async def test_create_account_okx_requires_passphrase(
        self, client: AsyncClient, auth_headers
    ):
        """OKX 必须提供 passphrase，否则 422"""
        resp = await client.post(
            "/api/v1/trading/accounts",
            headers=auth_headers,
            json={
                "exchange": "okx",
                "account_name": "okx-1",
                "api_key": "fake_api_key_value",
                "secret_key": "fake_secret_key_value",
                # 故意不提供 passphrase
            },
        )
        assert resp.status_code == 422

    async def test_create_account_validates_short_keys(
        self, client: AsyncClient, auth_headers
    ):
        """API key 太短应被 Pydantic 拦截"""
        resp = await client.post(
            "/api/v1/trading/accounts",
            headers=auth_headers,
            json={
                "exchange": "binance",
                "account_name": "binance-1",
                "api_key": "x",  # 太短，min_length=8
                "secret_key": "y",
            },
        )
        assert resp.status_code == 422

    async def test_create_account_unknown_exchange(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.post(
            "/api/v1/trading/accounts",
            headers=auth_headers,
            json={
                "exchange": "kraken",  # 不在 Literal 列表
                "account_name": "kraken-1",
                "api_key": "fake_api_key_value",
                "secret_key": "fake_secret_key_value",
            },
        )
        assert resp.status_code == 422

    async def test_delete_nonexistent_account_returns_404(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.delete(
            "/api/v1/trading/accounts/999999", headers=auth_headers
        )
        assert resp.status_code == 404


# ==================== 订单创建校验 ====================

class TestOrderValidation:
    async def test_create_order_unauthenticated(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/trading",
            json={
                "account_id": 1,
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "market",
                "quantity": "0.01",
            },
        )
        assert resp.status_code in (401, 403)

    async def test_create_order_zero_quantity_rejected(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.post(
            "/api/v1/trading",
            headers=auth_headers,
            json={
                "account_id": 1,
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "market",
                "quantity": "0",  # 必须 > 0
            },
        )
        assert resp.status_code == 422

    async def test_create_order_negative_account_id_rejected(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.post(
            "/api/v1/trading",
            headers=auth_headers,
            json={
                "account_id": -1,
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "market",
                "quantity": "0.01",
            },
        )
        assert resp.status_code == 422

    async def test_create_order_invalid_side_rejected(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.post(
            "/api/v1/trading",
            headers=auth_headers,
            json={
                "account_id": 1,
                "symbol": "BTCUSDT",
                "side": "long",  # 应当是 buy/sell
                "order_type": "market",
                "quantity": "0.01",
            },
        )
        assert resp.status_code == 422

    async def test_create_order_invalid_symbol_format(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.post(
            "/api/v1/trading",
            headers=auth_headers,
            json={
                "account_id": 1,
                "symbol": "btc-usdt",  # 不符合 [A-Z]{2,10}(USDT|...)
                "side": "buy",
                "order_type": "market",
                "quantity": "0.01",
            },
        )
        assert resp.status_code == 422

    async def test_create_order_negative_price_rejected(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.post(
            "/api/v1/trading",
            headers=auth_headers,
            json={
                "account_id": 1,
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "limit",
                "quantity": "0.01",
                "price": "-100",
            },
        )
        assert resp.status_code == 422

    async def test_create_order_account_not_found(
        self, client: AsyncClient, auth_headers
    ):
        """账户不存在 → 404"""
        resp = await client.post(
            "/api/v1/trading",
            headers=auth_headers,
            json={
                "account_id": 999_999,
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "market",
                "quantity": "0.01",
            },
        )
        assert resp.status_code == 404


# ==================== 持仓 / 订单查询 ====================

class TestPositionsAndOrdersAPI:
    async def test_get_positions_empty(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.get(
            "/api/v1/trading/positions", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_get_orders_empty(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.get("/api/v1/trading", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_get_orders_limit_validated(
        self, client: AsyncClient, auth_headers
    ):
        # limit > 500 应被 Pydantic 拒绝
        resp = await client.get(
            "/api/v1/trading?limit=99999", headers=auth_headers
        )
        assert resp.status_code == 422

    async def test_get_orders_limit_minimum_validated(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.get(
            "/api/v1/trading?limit=0", headers=auth_headers
        )
        assert resp.status_code == 422


# ==================== 紧急平仓确认机制 ====================

class TestEmergencyClose:
    async def test_emergency_close_requires_confirm(
        self, client: AsyncClient, auth_headers
    ):
        """confirm=false 应当被拒绝"""
        resp = await client.post(
            "/api/v1/trading/emergency-close-all",
            headers=auth_headers,
            json={"confirm": False},
        )
        assert resp.status_code == 400

    async def test_emergency_close_with_confirm_runs(
        self, client: AsyncClient, auth_headers
    ):
        """confirm=true 应当成功（无持仓时返回 0）"""
        resp = await client.post(
            "/api/v1/trading/emergency-close-all",
            headers=auth_headers,
            json={"confirm": True},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["closed_count"] == 0

    async def test_emergency_close_unauthenticated(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/trading/emergency-close-all",
            json={"confirm": True},
        )
        assert resp.status_code in (401, 403)

    async def test_emergency_close_missing_confirm_rejected(
        self, client: AsyncClient, auth_headers
    ):
        # confirm 是必填字段
        resp = await client.post(
            "/api/v1/trading/emergency-close-all",
            headers=auth_headers,
            json={},
        )
        assert resp.status_code == 422


# ==================== 取消订单 ====================

class TestCancelOrderAPI:
    async def test_cancel_nonexistent_order(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.post(
            "/api/v1/trading/999999/cancel", headers=auth_headers
        )
        assert resp.status_code == 404

    async def test_cancel_unauthenticated(self, client: AsyncClient):
        resp = await client.post("/api/v1/trading/1/cancel")
        assert resp.status_code in (401, 403)


# ==================== 止盈止损请求校验 ====================

class TestStopLossTakeProfitValidation:
    async def test_stop_loss_negative_price_rejected(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.post(
            "/api/v1/trading/1/stop-loss",
            headers=auth_headers,
            json={"account_id": 1, "stop_price": "-100"},
        )
        assert resp.status_code == 422

    async def test_take_profit_negative_price_rejected(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.post(
            "/api/v1/trading/1/take-profit",
            headers=auth_headers,
            json={"account_id": 1, "take_profit_price": "0"},
        )
        assert resp.status_code == 422

    async def test_stop_loss_unauthenticated(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/trading/1/stop-loss",
            json={"account_id": 1, "stop_price": "100"},
        )
        assert resp.status_code in (401, 403)
