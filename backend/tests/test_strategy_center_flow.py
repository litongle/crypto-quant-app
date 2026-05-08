"""
策略中心后端流转测试
"""

from unittest.mock import AsyncMock, patch

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from app.models.exchange import ExchangeAccount
from app.models.strategy import StrategyInstance


@pytest_asyncio.fixture(autouse=True)
async def isolate_strategy_instances(db_session):
    await db_session.execute(delete(StrategyInstance))
    await db_session.commit()
    yield
    await db_session.execute(delete(StrategyInstance))
    await db_session.commit()


@pytest_asyncio.fixture(autouse=True)
def mock_strategy_runner():
    with (
        patch(
            "app.core.strategy_runner.strategy_runner.start_instance",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.core.strategy_runner.strategy_runner.stop_instance",
            new=AsyncMock(return_value=None),
        ),
    ):
        yield


async def _create_strategy(client: AsyncClient, auth_headers: dict) -> dict:
    response = await client.post(
        "/api/v1/strategies/instances",
        headers=auth_headers,
        json={
            "name": "趋势策略",
            "templateId": "ma_cross",
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "params": {"fast_period": 5, "slow_period": 20},
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


async def _make_account(db_session, user_id: int, *, exchange: str = "binance") -> ExchangeAccount:
    account = ExchangeAccount(
        user_id=user_id,
        exchange=exchange,
        account_name="strategy-live",
        is_active=True,
        status="active",
    )
    account.set_api_key("FAKE_API_KEY_FOR_TEST_AAAAA")
    account.set_secret_key("FAKE_SECRET_KEY_FOR_TEST_BBBBB")
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)
    return account


class TestStrategyCenterFlow:
    async def test_create_strategy_saved_to_library(self, client: AsyncClient, auth_headers):
        created = await _create_strategy(client, auth_headers)
        instance_id = created["id"]
        assert created["status"] == "draft"

        detail_response = await client.get(
            f"/api/v1/strategies/instances/{instance_id}",
            headers=auth_headers,
        )
        assert detail_response.status_code == 200

        detail = detail_response.json()["data"]
        assert detail["status"] == "draft"
        assert detail["workspaceState"] == "library"
        assert detail["sourceInstanceId"] is None
        assert detail["createdAt"].endswith("Z")
        assert detail["updatedAt"].endswith("Z")
        assert detail["lastStartedAt"] is None
        assert detail["lastStoppedAt"] is None

    async def test_start_strategy_moves_to_running_workspace(
        self, client: AsyncClient, auth_headers
    ):
        created = await _create_strategy(client, auth_headers)
        instance_id = created["id"]

        start_response = await client.post(
            f"/api/v1/strategies/instances/{instance_id}/start",
            headers=auth_headers,
        )
        assert start_response.status_code == 200
        assert start_response.json()["data"]["status"] == "running"

        detail_response = await client.get(
            f"/api/v1/strategies/instances/{instance_id}",
            headers=auth_headers,
        )
        detail = detail_response.json()["data"]
        assert detail["status"] == "running"
        assert detail["workspaceState"] == "running"
        assert detail["lastStartedAt"] is not None
        assert detail["lastStartedAt"].endswith("Z")
        assert detail["lastStoppedAt"] is None

    async def test_stop_strategy_returns_to_library_and_records_time(
        self, client: AsyncClient, auth_headers
    ):
        created = await _create_strategy(client, auth_headers)
        instance_id = created["id"]

        await client.post(
            f"/api/v1/strategies/instances/{instance_id}/start",
            headers=auth_headers,
        )
        stop_response = await client.post(
            f"/api/v1/strategies/instances/{instance_id}/stop",
            headers=auth_headers,
        )
        assert stop_response.status_code == 200
        assert stop_response.json()["data"]["status"] == "stopped"

        detail_response = await client.get(
            f"/api/v1/strategies/instances/{instance_id}",
            headers=auth_headers,
        )
        detail = detail_response.json()["data"]
        assert detail["status"] == "stopped"
        assert detail["workspaceState"] == "library"
        assert detail["lastStartedAt"] is not None
        assert detail["lastStoppedAt"] is not None
        assert detail["lastStartedAt"].endswith("Z")
        assert detail["lastStoppedAt"].endswith("Z")

    async def test_clone_running_strategy_creates_draft_copy(
        self, client: AsyncClient, auth_headers
    ):
        created = await _create_strategy(client, auth_headers)
        instance_id = created["id"]

        await client.post(
            f"/api/v1/strategies/instances/{instance_id}/start",
            headers=auth_headers,
        )
        clone_response = await client.post(
            f"/api/v1/strategies/instances/{instance_id}/clone-draft",
            headers=auth_headers,
        )
        assert clone_response.status_code == 200

        clone = clone_response.json()["data"]
        assert clone["status"] == "draft"
        assert clone["workspaceState"] == "draft"
        assert clone["sourceInstanceId"] == instance_id
        assert clone["lastStartedAt"] is None
        assert clone["lastStoppedAt"] is None

        original_detail_response = await client.get(
            f"/api/v1/strategies/instances/{instance_id}",
            headers=auth_headers,
        )
        original = original_detail_response.json()["data"]
        assert original["status"] == "running"
        assert original["workspaceState"] == "running"

    async def test_clone_library_strategy_creates_draft_copy(
        self, client: AsyncClient, auth_headers
    ):
        created = await _create_strategy(client, auth_headers)
        instance_id = created["id"]

        clone_response = await client.post(
            f"/api/v1/strategies/instances/{instance_id}/clone-draft",
            headers=auth_headers,
        )
        assert clone_response.status_code == 200

        clone = clone_response.json()["data"]
        assert clone["status"] == "draft"
        assert clone["workspaceState"] == "draft"
        assert clone["sourceInstanceId"] == instance_id

        original_detail_response = await client.get(
            f"/api/v1/strategies/instances/{instance_id}",
            headers=auth_headers,
        )
        original = original_detail_response.json()["data"]
        assert original["status"] == "draft"
        assert original["workspaceState"] == "library"

    async def test_clone_same_strategy_reuses_existing_draft(
        self, client: AsyncClient, auth_headers
    ):
        created = await _create_strategy(client, auth_headers)
        instance_id = created["id"]

        first_clone_response = await client.post(
            f"/api/v1/strategies/instances/{instance_id}/clone-draft",
            headers=auth_headers,
        )
        assert first_clone_response.status_code == 200
        first_clone = first_clone_response.json()["data"]

        second_clone_response = await client.post(
            f"/api/v1/strategies/instances/{instance_id}/clone-draft",
            headers=auth_headers,
        )
        assert second_clone_response.status_code == 200
        second_clone = second_clone_response.json()["data"]

        assert second_clone["id"] == first_clone["id"]
        assert second_clone["workspaceState"] == "draft"
        assert second_clone["sourceInstanceId"] == instance_id

    async def test_running_strategy_cannot_be_updated_directly(
        self, client: AsyncClient, auth_headers
    ):
        created = await _create_strategy(client, auth_headers)
        instance_id = created["id"]

        await client.post(
            f"/api/v1/strategies/instances/{instance_id}/start",
            headers=auth_headers,
        )
        update_response = await client.put(
            f"/api/v1/strategies/instances/{instance_id}",
            headers=auth_headers,
            json={"name": "不能直接改", "params": {"fast_period": 8}},
        )
        assert update_response.status_code == 400
        assert "复制为工作台草案" in update_response.json()["detail"]

    async def test_library_strategy_cannot_be_updated_directly(
        self, client: AsyncClient, auth_headers
    ):
        created = await _create_strategy(client, auth_headers)
        instance_id = created["id"]

        update_response = await client.put(
            f"/api/v1/strategies/instances/{instance_id}",
            headers=auth_headers,
            json={"name": "直接改正式策略", "params": {"fast_period": 8}},
        )
        assert update_response.status_code == 400
        assert "复制为工作台草案" in update_response.json()["detail"]

    async def test_delete_original_strategy_after_clone_keeps_draft_usable(
        self, client: AsyncClient, auth_headers
    ):
        created = await _create_strategy(client, auth_headers)
        instance_id = created["id"]

        await client.post(
            f"/api/v1/strategies/instances/{instance_id}/start",
            headers=auth_headers,
        )
        clone_response = await client.post(
            f"/api/v1/strategies/instances/{instance_id}/clone-draft",
            headers=auth_headers,
        )
        clone = clone_response.json()["data"]

        await client.post(
            f"/api/v1/strategies/instances/{instance_id}/stop",
            headers=auth_headers,
        )
        delete_response = await client.delete(
            f"/api/v1/strategies/instances/{instance_id}",
            headers=auth_headers,
        )
        assert delete_response.status_code == 200

        draft_detail_response = await client.get(
            f"/api/v1/strategies/instances/{clone['id']}",
            headers=auth_headers,
        )
        assert draft_detail_response.status_code == 200
        draft = draft_detail_response.json()["data"]
        assert draft["status"] == "draft"
        assert draft["workspaceState"] == "draft"
        assert draft["sourceInstanceId"] is None

    async def test_clone_draft_respects_instance_quota(self, client: AsyncClient, auth_headers):
        created = await _create_strategy(client, auth_headers)
        instance_id = created["id"]

        await client.post(
            f"/api/v1/strategies/instances/{instance_id}/start",
            headers=auth_headers,
        )

        for index in range(1, 20):
            response = await client.post(
                "/api/v1/strategies/instances",
                headers=auth_headers,
                json={
                    "name": f"策略补位{index}",
                    "templateId": "ma_cross",
                    "exchange": "binance",
                    "symbol": "BTCUSDT",
                    "params": {"fast_period": 5, "slow_period": 20},
                },
            )
            assert response.status_code == 201

        clone_response = await client.post(
            f"/api/v1/strategies/instances/{instance_id}/clone-draft",
            headers=auth_headers,
        )
        assert clone_response.status_code == 429

    async def test_start_strategy_does_not_persist_running_state_when_runner_refuses(
        self, client: AsyncClient, auth_headers
    ):
        created = await _create_strategy(client, auth_headers)
        instance_id = created["id"]

        with patch(
            "app.core.strategy_runner.strategy_runner.start_instance",
            new=AsyncMock(return_value=False),
        ):
            start_response = await client.post(
                f"/api/v1/strategies/instances/{instance_id}/start",
                headers=auth_headers,
            )
        assert start_response.status_code == 409

        detail_response = await client.get(
            f"/api/v1/strategies/instances/{instance_id}",
            headers=auth_headers,
        )
        detail = detail_response.json()["data"]
        assert detail["status"] == "draft"
        assert detail["workspaceState"] == "library"
        assert detail["lastStartedAt"] is None

    async def test_start_live_strategy_requires_bound_account(
        self, client: AsyncClient, auth_headers
    ):
        response = await client.post(
            "/api/v1/strategies/instances",
            headers=auth_headers,
            json={
                "name": "RSI layered live",
                "templateId": "rsi_layered",
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "params": {"auto_trade": True},
            },
        )
        assert response.status_code == 201
        instance_id = response.json()["data"]["id"]

        start_response = await client.post(
            f"/api/v1/strategies/instances/{instance_id}/start",
            headers=auth_headers,
        )
        assert start_response.status_code == 400
        assert "绑定交易所账户" in start_response.json()["detail"]

    async def test_live_instance_detail_requires_auto_trade_enabled(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        account = await _make_account(db_session, test_user.id)
        response = await client.post(
            "/api/v1/strategies/instances",
            headers=auth_headers,
            json={
                "name": "MA prebind",
                "templateId": "ma_cross",
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "accountId": account.id,
                "params": {"fast_period": 5, "slow_period": 20},
            },
        )
        assert response.status_code == 201
        instance_id = response.json()["data"]["id"]

        detail_response = await client.get(
            f"/api/v1/strategies/instances/{instance_id}",
            headers=auth_headers,
        )
        assert detail_response.status_code == 200
        assert detail_response.json()["data"]["isLive"] is False

    async def test_create_multi_symbol_with_account_rejected(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        account = await _make_account(db_session, test_user.id)
        response = await client.post(
            "/api/v1/strategies/instances",
            headers=auth_headers,
            json={
                "name": "multi live",
                "templateId": "multi_symbol",
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "accountId": account.id,
                "params": {},
            },
        )
        assert response.status_code == 400
        assert "暂不支持真实自动下单" in response.json()["detail"]

    async def test_save_draft_to_library_updates_workspace_and_trade_config(
        self, client: AsyncClient, auth_headers
    ):
        created = await _create_strategy(client, auth_headers)
        instance_id = created["id"]

        await client.post(
            f"/api/v1/strategies/instances/{instance_id}/start",
            headers=auth_headers,
        )
        clone_response = await client.post(
            f"/api/v1/strategies/instances/{instance_id}/clone-draft",
            headers=auth_headers,
        )
        draft_id = clone_response.json()["data"]["id"]

        update_response = await client.put(
            f"/api/v1/strategies/instances/{draft_id}",
            headers=auth_headers,
            json={
                "name": "编辑后的草案",
                "exchange": "okx",
                "symbol": "ethusdt",
                "accountId": None,
                "params": {"fast_period": 8, "slow_period": 30},
                "workspaceState": "library",
            },
        )
        assert update_response.status_code == 200

        detail_response = await client.get(
            f"/api/v1/strategies/instances/{draft_id}",
            headers=auth_headers,
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]
        assert detail["name"] == "编辑后的草案"
        assert detail["workspaceState"] == "library"
        assert detail["exchange"] == "okx"
        assert detail["symbol"] == "ETHUSDT"
        assert detail["accountId"] is None
        assert detail["params"]["fast_period"] == 8

    async def test_status_stopped_filter_includes_never_started_library_strategies(
        self, client: AsyncClient, auth_headers
    ):
        created = await _create_strategy(client, auth_headers)
        instance_id = created["id"]

        list_response = await client.get(
            "/api/v1/strategies/instances?status=stopped",
            headers=auth_headers,
        )
        assert list_response.status_code == 200

        ids = [item["id"] for item in list_response.json()["data"]]
        assert instance_id in ids

    async def test_status_stopped_filter_excludes_workbench_drafts(
        self, client: AsyncClient, auth_headers
    ):
        created = await _create_strategy(client, auth_headers)
        instance_id = created["id"]

        clone_response = await client.post(
            f"/api/v1/strategies/instances/{instance_id}/clone-draft",
            headers=auth_headers,
        )
        assert clone_response.status_code == 200
        draft_id = clone_response.json()["data"]["id"]

        list_response = await client.get(
            "/api/v1/strategies/instances?status=stopped",
            headers=auth_headers,
        )
        assert list_response.status_code == 200

        ids = [item["id"] for item in list_response.json()["data"]]
        assert instance_id in ids
        assert draft_id not in ids
