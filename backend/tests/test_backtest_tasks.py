"""
后台回测任务管理器测试。

只测纯任务管理器（submit / get / cancel），不走 HTTP / DB —— BacktestService
被 mock 掉，避免拉网络 / 起 SQLite engine。
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core import backtest_tasks


@pytest.fixture(autouse=True)
def _reset_tasks():
    """每个用例独立的任务表，避免相互污染。"""
    backtest_tasks._reset_for_tests()
    yield
    backtest_tasks._reset_for_tests()


def _payload() -> dict[str, Any]:
    return {
        "template_id": "rsi",
        "symbol": "BTCUSDT",
        "exchange": "binance",
        "market": "spot",
        "start_date": "2026-01-01",
        "end_date": "2026-02-01",
        "initial_capital": 10000.0,
        "params": {},
        "analysis_window": None,
    }


async def test_submit_returns_task_id_and_pending_status():
    """submit 立刻返 hex task_id；初始 status 是 pending 或 running（已被调度）。"""

    # mock service：阻塞够久，让我们能观察到 pending/running 状态而不是已 completed
    async def slow_execute(**_kwargs):
        await asyncio.sleep(0.5)
        return {"totalReturn": 0.0}

    # _save_backtest_history 也要 mock 掉，避免触碰真实 DB
    with (
        patch(
            "app.services.backtest_service.BacktestService.execute_backtest",
            new=AsyncMock(side_effect=slow_execute),
        ),
        patch(
            "app.api.v1.backtest._save_backtest_history",
            new=AsyncMock(return_value=None),
        ),
    ):
        task_id = backtest_tasks.submit(user_id=1, payload=_payload())

        assert isinstance(task_id, str)
        assert len(task_id) == 32  # uuid4().hex

        state = backtest_tasks.get(task_id)
        assert state is not None
        assert state["status"] in ("pending", "running")
        assert state["user_id"] == 1
        assert state["progress"] in (0, 10, 30)
        assert "future" not in state  # 公开视图不该有 asyncio.Task

        # 兜个底：让后台 task 跑完，避免 asyncio warning
        await asyncio.sleep(0.7)


async def test_get_returns_completed_after_run():
    """mock BacktestService 直接返一个 dict，等任务跑完检查 status=completed。"""
    fake_result = {
        "totalReturn": 123.45,
        "totalReturnPercent": 1.2,
        "sharpeRatio": 0.8,
        "maxDrawdown": 5.0,
        "winRate": 60.0,
        "totalTrades": 10,
    }

    with (
        patch(
            "app.services.backtest_service.BacktestService.execute_backtest",
            new=AsyncMock(return_value=fake_result),
        ),
        patch(
            "app.api.v1.backtest._save_backtest_history",
            new=AsyncMock(return_value=None),
        ),
    ):
        task_id = backtest_tasks.submit(user_id=42, payload=_payload())

        # 等 0.5s 足够后台 task 跑完（mock 是同步 return）
        for _ in range(20):
            await asyncio.sleep(0.05)
            state = backtest_tasks.get(task_id)
            assert state is not None
            if state["status"] == "completed":
                break

        state = backtest_tasks.get(task_id)
        assert state is not None
        assert state["status"] == "completed"
        assert state["progress"] == 100
        assert state["stage"] == "done"
        assert state["result"] == fake_result
        assert state["error"] is None
        assert state["completed_at"] is not None


async def test_get_404_when_unknown_task_id():
    """未知 task_id → get 返 None（路由层会映射成 404）。"""
    assert backtest_tasks.get("nonexistent_task_id_xxx") is None
    assert backtest_tasks.cancel("nonexistent_task_id_xxx") is False


async def test_failed_task_reports_error_from_service_dict():
    """service 返 {'error': ...} 时被 task 标记为 failed。"""
    err_result = {"error": "回测数据不足", "code": 4001}

    with (
        patch(
            "app.services.backtest_service.BacktestService.execute_backtest",
            new=AsyncMock(return_value=err_result),
        ),
        patch(
            "app.api.v1.backtest._save_backtest_history",
            new=AsyncMock(return_value=None),
        ),
    ):
        task_id = backtest_tasks.submit(user_id=1, payload=_payload())
        for _ in range(20):
            await asyncio.sleep(0.05)
            state = backtest_tasks.get(task_id)
            if state and state["status"] == "failed":
                break

        state = backtest_tasks.get(task_id)
        assert state is not None
        assert state["status"] == "failed"
        assert "回测数据不足" in (state["error"] or "")
