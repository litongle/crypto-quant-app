"""
策略 API 集成测试 — 模板查询、实例 CRUD、规则校验
"""

from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import delete

from app.models.exchange import ExchangeAccount, Position
from app.models.order import Order
from app.models.strategy import StrategyInstance

# ==================== 模板查询 ====================


class TestStrategyTemplatesAPI:
    async def test_get_templates_no_auth_required(self, client: AsyncClient):
        """模板列表是公开的"""
        resp = await client.get("/api/v1/strategies/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) > 0

    async def test_template_has_required_fields(self, client: AsyncClient):
        resp = await client.get("/api/v1/strategies/templates")
        templates = resp.json()["data"]
        for tpl in templates:
            assert "id" in tpl
            assert "name" in tpl

    async def test_templates_are_sorted_for_creation_ux(self, client: AsyncClient):
        resp = await client.get("/api/v1/strategies/templates")
        templates = resp.json()["data"]
        assert [tpl["id"] for tpl in templates] == [
            "rule_custom",
            "rsi_layered",
            "ma_cross",
            "rsi",
            "bollinger",
            "grid",
            "martingale",
            "dca",
        ]

    async def test_template_live_trading_flags_match_capability(self, client: AsyncClient):
        resp = await client.get("/api/v1/strategies/templates")
        templates = {tpl["id"]: tpl for tpl in resp.json()["data"]}
        assert templates["rsi_layered"]["liveTradingSupported"] is True
        assert templates["dca"]["liveTradingSupported"] is True


# ==================== 实例查询 ====================


class TestStrategyInstancesAPI:
    async def test_get_instances_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/strategies/instances")
        assert resp.status_code in (401, 403)

    async def test_get_instances_empty(self, client: AsyncClient, auth_headers):
        resp = await client.get("/api/v1/strategies/instances", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_get_instances_status_filter(self, client: AsyncClient, auth_headers):
        resp = await client.get(
            "/api/v1/strategies/instances?status=running",
            headers=auth_headers,
        )
        assert resp.status_code == 200

    async def test_get_instance_snapshot_filters_positions_and_orders(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        await db_session.execute(delete(Order))
        await db_session.execute(delete(Position))
        await db_session.execute(delete(StrategyInstance))
        await db_session.commit()

        account = ExchangeAccount(
            user_id=test_user.id,
            exchange="binance",
            account_name="snapshot-account",
            is_active=True,
            status="active",
        )
        account.set_api_key("FAKE_API_KEY_FOR_TEST_AAAAA")
        account.set_secret_key("FAKE_SECRET_KEY_FOR_TEST_BBBBB")
        db_session.add(account)
        await db_session.flush()

        first = StrategyInstance(
            user_id=test_user.id,
            template_id=1,
            name="first",
            symbol="BTCUSDT",
            exchange="binance",
            direction="both",
            params={},
            risk_params={},
            account_id=account.id,
            status="running",
            workspace_state="running",
        )
        second = StrategyInstance(
            user_id=test_user.id,
            template_id=1,
            name="second",
            symbol="ETHUSDT",
            exchange="binance",
            direction="both",
            params={},
            risk_params={},
            account_id=account.id,
            status="running",
            workspace_state="running",
        )
        db_session.add_all([first, second])
        await db_session.flush()

        db_session.add_all(
            [
                Position(
                    account_id=account.id,
                    symbol="BTCUSDT",
                    side="long",
                    quantity=Decimal("1"),
                    entry_price=Decimal("60000"),
                    current_price=Decimal("61000"),
                    leverage=1,
                    status="open",
                    strategy_instance_id=first.id,
                ),
                Position(
                    account_id=account.id,
                    symbol="ETHUSDT",
                    side="long",
                    quantity=Decimal("2"),
                    entry_price=Decimal("3000"),
                    current_price=Decimal("3100"),
                    leverage=1,
                    status="open",
                    strategy_instance_id=second.id,
                ),
                Order(
                    account_id=account.id,
                    symbol="BTCUSDT",
                    side="buy",
                    order_type="market",
                    quantity=Decimal("1"),
                    filled_quantity=Decimal("1"),
                    avg_fill_price=Decimal("60000"),
                    order_value=Decimal("60000"),
                    commission=Decimal("0"),
                    status="filled",
                    strategy_instance_id=first.id,
                ),
                Order(
                    account_id=account.id,
                    symbol="ETHUSDT",
                    side="buy",
                    order_type="market",
                    quantity=Decimal("2"),
                    filled_quantity=Decimal("2"),
                    avg_fill_price=Decimal("3000"),
                    order_value=Decimal("6000"),
                    commission=Decimal("0"),
                    status="filled",
                    strategy_instance_id=second.id,
                ),
            ]
        )
        await db_session.commit()

        resp = await client.get(
            f"/api/v1/strategies/instances/{first.id}/snapshot",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["positions"]) == 1
        assert data["positions"][0]["strategyInstanceId"] == first.id
        assert data["positions"][0]["symbol"] == "BTCUSDT"
        assert len(data["orders"]) == 1
        assert data["orders"][0]["strategyInstanceId"] == first.id
        assert data["orders"][0]["symbol"] == "BTCUSDT"


# ==================== 实例创建校验 ====================


class TestCreateStrategyAPI:
    async def test_create_unauthenticated(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/strategies/instances",
            json={
                "name": "test-strategy",
                "templateId": "ma_cross",
                "exchange": "binance",
                "symbol": "BTCUSDT",
            },
        )
        assert resp.status_code in (401, 403)

    async def test_create_missing_required_fields(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            "/api/v1/strategies/instances",
            headers=auth_headers,
            json={"name": "x"},
        )
        assert resp.status_code == 422

    async def test_create_empty_name_rejected(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            "/api/v1/strategies/instances",
            headers=auth_headers,
            json={
                "name": "",  # min_length=1
                "templateId": "ma_cross",
                "exchange": "binance",
                "symbol": "BTCUSDT",
            },
        )
        assert resp.status_code == 422

    async def test_create_unknown_template_returns_404(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            "/api/v1/strategies/instances",
            headers=auth_headers,
            json={
                "name": "test",
                "templateId": "no_such_template_xyz",
                "exchange": "binance",
                "symbol": "BTCUSDT",
            },
        )
        assert resp.status_code == 404


# ==================== 实例 IDOR / 错误处理 ====================


class TestStrategyInstanceErrors:
    async def test_get_nonexistent_instance(self, client: AsyncClient, auth_headers):
        resp = await client.get("/api/v1/strategies/instances/999999", headers=auth_headers)
        assert resp.status_code == 404

    async def test_start_nonexistent_instance(self, client: AsyncClient, auth_headers):
        resp = await client.post("/api/v1/strategies/instances/999999/start", headers=auth_headers)
        assert resp.status_code == 404

    async def test_stop_nonexistent_instance(self, client: AsyncClient, auth_headers):
        resp = await client.post("/api/v1/strategies/instances/999999/stop", headers=auth_headers)
        assert resp.status_code == 404

    async def test_delete_nonexistent_instance(self, client: AsyncClient, auth_headers):
        resp = await client.delete("/api/v1/strategies/instances/999999", headers=auth_headers)
        assert resp.status_code == 404

    async def test_performance_nonexistent_instance(self, client: AsyncClient, auth_headers):
        resp = await client.get(
            "/api/v1/strategies/instances/999999/performance",
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ==================== 规则校验 ====================


class TestValidateRulesAPI:
    async def test_validate_rules_unauthenticated(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/strategies/validate-rules",
            json={"rules": {}},
        )
        assert resp.status_code in (401, 403)

    async def test_validate_empty_rules(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            "/api/v1/strategies/validate-rules",
            headers=auth_headers,
            json={"rules": {}},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "valid" in data
        assert "errors" in data
        assert "description" in data

    async def test_validate_simple_rule(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            "/api/v1/strategies/validate-rules",
            headers=auth_headers,
            json={
                "rules": {
                    "buy_rules": {
                        "logic": "AND",
                        "conditions": [
                            {
                                "left": "rsi(14)",
                                "operator": "<",
                                "right": 30,
                            }
                        ],
                    },
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "valid" in data

    async def test_validate_rules_missing_payload(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            "/api/v1/strategies/validate-rules",
            headers=auth_headers,
            json={},
        )
        assert resp.status_code == 422
