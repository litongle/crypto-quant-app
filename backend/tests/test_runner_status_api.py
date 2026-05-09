from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_runner_status_no_instances(client, auth_headers):
    with (
        patch("app.api.v1.strategies.get_exchange_adapter") as mock_adapter,
        patch("app.core.strategy_runner.strategy_runner._runners", {}),
        patch("app.core.strategy_runner.strategy_runner._running", False),
    ):
        mock_adapter.return_value.get_ticker = AsyncMock(return_value={"price": "1"})
        resp = await client.get("/api/v1/strategies/runner/status", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["strategy_runner"]["task_count"] == 0
    assert body["strategy_runner"]["alive_count"] == 0
    assert "last_heartbeat" in body["strategy_runner"]
    assert isinstance(body["exchanges"], list)


@pytest.mark.asyncio
async def test_runner_status_with_running_instance(client, auth_headers):
    class RunningTask:
        @staticmethod
        def done():
            return False

    with (
        patch("app.api.v1.strategies.get_exchange_adapter") as mock_adapter,
        patch("app.core.strategy_runner.strategy_runner._runners", {1: RunningTask()}),
        patch("app.core.strategy_runner.strategy_runner._running", True),
    ):
        mock_adapter.return_value.get_ticker = AsyncMock(return_value={"price": "1"})
        resp = await client.get("/api/v1/strategies/runner/status", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["strategy_runner"]["task_count"] == 1
    assert body["strategy_runner"]["alive_count"] == 1


@pytest.mark.asyncio
async def test_runner_status_exchange_failure(client, auth_headers):
    class BrokenAdapter:
        async def get_ticker(self, symbol):
            raise RuntimeError(f"{symbol} unavailable")

    with (
        patch("app.api.v1.strategies.get_exchange_adapter", return_value=BrokenAdapter()),
        patch("app.core.strategy_runner.strategy_runner._runners", {}),
        patch("app.core.strategy_runner.strategy_runner._running", True),
    ):
        resp = await client.get("/api/v1/strategies/runner/status", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()["data"]
    failed = [item for item in body["exchanges"] if not item["ws_connected"]]
    assert len(failed) >= 1
    assert "error" in failed[0]
