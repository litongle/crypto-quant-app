"""
回测后台任务管理器

POST /backtest/run 不再同步阻塞 30s-3min；改成：
- submit() 创建 asyncio.Task 在后台跑 BacktestService.execute_backtest
- 前端轮询 get(task_id) 拿 status / progress / result
- 用户可以 cancel(task_id) 主动停掉

内存存储，进程重启即丢；回测短，可接受。
不引入 Celery / RQ / dramatiq 等额外依赖。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# 全局任务表：{task_id: state_dict}
_tasks: dict[str, dict[str, Any]] = {}
_lock = asyncio.Lock()


def _new_task_id() -> str:
    return uuid.uuid4().hex


def _public_view(state: dict[str, Any]) -> dict[str, Any]:
    """对外暴露的字段：剔除 future（asyncio.Task 不可 JSON 序列化）。"""
    return {k: v for k, v in state.items() if k != "future"}


async def _runner(task_id: str, user_id: int, payload: dict[str, Any]) -> None:
    """实际跑回测的协程，挂在 asyncio.Task 上后台执行。

    progress 简化：只在阶段切换时跳档（10 拉K线/30 引擎中/100 完成）。
    要做细粒度需要改 BacktestService 加回调，本期不动 service。
    """
    state = _tasks.get(task_id)
    if state is None:
        return  # 极端：刚 submit 就被外部清掉

    # 延迟 import 避免循环依赖（service 不应该反向依赖 task 管理器）
    from app.api.v1.backtest import _save_backtest_history
    from app.database import get_db_context
    from app.services.backtest_service import BacktestService

    try:
        state["status"] = "running"
        state["stage"] = "fetching_klines"
        state["progress"] = 10

        service = BacktestService()
        # 拉 K 线 + 跑引擎是一个原子调用（service 内部串行）；
        # 拉完到引擎之间没有 hook，所以只能在调用前/后切档
        state["stage"] = "running_engine"
        state["progress"] = 30

        result = await service.execute_backtest(
            template_id=payload["template_id"],
            symbol=payload["symbol"],
            exchange=payload.get("exchange", "binance"),
            market=payload.get("market", "spot"),
            start_date=payload["start_date"],
            end_date=payload["end_date"],
            initial_capital=payload.get("initial_capital", 100000.0),
            params=payload.get("params") or {},
            analysis_window=payload.get("analysis_window"),
        )

        # service 返回的 error 视作业务失败（数据不足、不支持的策略等）
        if isinstance(result, dict) and "error" in result:
            state["status"] = "failed"
            state["error"] = str(result["error"])
            state["result"] = result  # 把 code/detail 也带回前端
            state["progress"] = 100
            state["stage"] = "done"
            state["completed_at"] = datetime.now(UTC)
            return

        state["stage"] = "saving"
        state["progress"] = 90

        # 保存历史（与同步路由一致的容错策略：失败只记 log，不影响返回）
        try:
            async with get_db_context() as session:
                await _save_backtest_history(
                    session=session,
                    user_id=user_id,
                    template_id=payload["template_id"],
                    symbol=payload["symbol"],
                    exchange=payload.get("exchange", "binance"),
                    start_date=payload["start_date"],
                    end_date=payload["end_date"],
                    initial_capital=payload.get("initial_capital", 100000.0),
                    params=payload.get("params") or {},
                    result=result,
                )
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.warning("[backtest-task] 保存回测历史临时失败: %s", e)
        except ValueError as e:
            logger.error("[backtest-task] 保存回测历史数据格式错误: %s", e)
        except Exception as e:
            logger.exception("[backtest-task] 保存回测历史未预期错误: %s", e)

        state["result"] = result
        state["status"] = "completed"
        state["progress"] = 100
        state["stage"] = "done"
        state["completed_at"] = datetime.now(UTC)
    except asyncio.CancelledError:
        # 调用方 cancel() 触发：标记为 cancelled 并向上传递
        state["status"] = "cancelled"
        state["error"] = "用户取消"
        state["completed_at"] = datetime.now(UTC)
        raise
    except Exception as e:
        logger.exception("[backtest-task] 后台回测失败 task_id=%s: %s", task_id, e)
        state["status"] = "failed"
        state["error"] = str(e) or e.__class__.__name__
        state["progress"] = 100
        state["stage"] = "done"
        state["completed_at"] = datetime.now(UTC)


def submit(user_id: int, payload: dict[str, Any]) -> str:
    """创建任务并立即返回 task_id；后台协程异步跑。"""
    task_id = _new_task_id()
    state: dict[str, Any] = {
        "status": "pending",
        "progress": 0,
        "stage": "queued",
        "user_id": user_id,
        "started_at": datetime.now(UTC),
        "completed_at": None,
        "result": None,
        "error": None,
        "future": None,
    }
    _tasks[task_id] = state
    # 顺手清一次老任务（廉价，不阻塞）
    cleanup_old()
    future = asyncio.create_task(_runner(task_id, user_id, payload), name=f"backtest-{task_id}")
    state["future"] = future
    return task_id


def get(task_id: str) -> dict[str, Any] | None:
    """查询任务状态。返回不含 future 的副本。"""
    state = _tasks.get(task_id)
    if state is None:
        return None
    return _public_view(state)


def cancel(task_id: str) -> bool:
    """请求取消任务。返回是否成功发起取消（不保证已停止）。"""
    state = _tasks.get(task_id)
    if state is None:
        return False
    if state["status"] in ("completed", "failed", "cancelled"):
        return False
    future = state.get("future")
    if future is None or future.done():
        return False
    return future.cancel()


def cleanup_old(max_age_seconds: int = 3600) -> int:
    """清理已结束且超过 max_age 秒的任务，避免内存膨胀。返回清理数。"""
    cutoff = datetime.now(UTC) - timedelta(seconds=max_age_seconds)
    to_remove = [
        tid
        for tid, st in _tasks.items()
        if st["status"] in ("completed", "failed", "cancelled")
        and st.get("completed_at") is not None
        and st["completed_at"] < cutoff
    ]
    for tid in to_remove:
        _tasks.pop(tid, None)
    return len(to_remove)


def _reset_for_tests() -> None:
    """测试用：清空全局状态。"""
    _tasks.clear()
