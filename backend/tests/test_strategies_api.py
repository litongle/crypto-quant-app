"""
策略 API 集成测试 — 模板查询、实例 CRUD、规则校验
"""
import pytest
from httpx import AsyncClient


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


# ==================== 实例查询 ====================

class TestStrategyInstancesAPI:
    async def test_get_instances_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/strategies/instances")
        assert resp.status_code in (401, 403)

    async def test_get_instances_empty(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.get(
            "/api/v1/strategies/instances", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_get_instances_status_filter(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.get(
            "/api/v1/strategies/instances?status=running",
            headers=auth_headers,
        )
        assert resp.status_code == 200


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

    async def test_create_missing_required_fields(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.post(
            "/api/v1/strategies/instances",
            headers=auth_headers,
            json={"name": "x"},
        )
        assert resp.status_code == 422

    async def test_create_empty_name_rejected(
        self, client: AsyncClient, auth_headers
    ):
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

    async def test_create_unknown_template_returns_404(
        self, client: AsyncClient, auth_headers
    ):
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
    async def test_get_nonexistent_instance(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.get(
            "/api/v1/strategies/instances/999999", headers=auth_headers
        )
        assert resp.status_code == 404

    async def test_start_nonexistent_instance(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.post(
            "/api/v1/strategies/instances/999999/start", headers=auth_headers
        )
        assert resp.status_code == 404

    async def test_stop_nonexistent_instance(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.post(
            "/api/v1/strategies/instances/999999/stop", headers=auth_headers
        )
        assert resp.status_code == 404

    async def test_delete_nonexistent_instance(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.delete(
            "/api/v1/strategies/instances/999999", headers=auth_headers
        )
        assert resp.status_code == 404

    async def test_performance_nonexistent_instance(
        self, client: AsyncClient, auth_headers
    ):
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

    async def test_validate_empty_rules(
        self, client: AsyncClient, auth_headers
    ):
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

    async def test_validate_simple_rule(
        self, client: AsyncClient, auth_headers
    ):
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

    async def test_validate_rules_missing_payload(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.post(
            "/api/v1/strategies/validate-rules",
            headers=auth_headers,
            json={},
        )
        assert resp.status_code == 422
