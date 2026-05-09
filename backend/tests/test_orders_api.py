"""交易账户 / 持仓 API 集成测试。"""

from httpx import AsyncClient

# ==================== 账户管理 ====================


class TestAccountsAPI:
    async def test_get_accounts_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/trading/accounts")
        assert resp.status_code in (401, 403)

    async def test_get_accounts_returns_empty_when_no_accounts(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.get("/api/v1/trading/accounts", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    async def test_create_account_okx_requires_passphrase(self, client: AsyncClient, auth_headers):
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

    async def test_create_account_validates_short_keys(self, client: AsyncClient, auth_headers):
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

    async def test_create_account_unknown_exchange(self, client: AsyncClient, auth_headers):
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

    async def test_delete_nonexistent_account_returns_404(self, client: AsyncClient, auth_headers):
        resp = await client.delete("/api/v1/trading/accounts/999999", headers=auth_headers)
        assert resp.status_code == 404


# ==================== 持仓查询 ====================


class TestPositionsAndOrdersAPI:
    async def test_get_positions_empty(self, client: AsyncClient, auth_headers):
        resp = await client.get("/api/v1/trading/positions", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"] == []

