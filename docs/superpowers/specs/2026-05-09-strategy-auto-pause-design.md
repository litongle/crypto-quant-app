# 策略自停 + 异常告警（v1）实现规格

**目标读者**: AI 编码代理（codex / Claude Code）
**变更面**: 1 model 字段 · 1 migration · `StrategyRunner` ~8 处改造 · 1 段 config · 1 套 pytest
**前置阅读**: 无；按本文件按部就班执行即可

---

## 0. 一句话目标

策略运行时遇到 3 类异常（连续运行时异常 / 连续下单失败 / 心跳超时）时，自动把 `StrategyInstance.status` 从 `running` 切到 `paused`，记录原因，推送 Telegram 告警；不做自动恢复。

---

## 1. 现状快照（不要修改的事实）

- 单例 runner: `backend/app/core/strategy_runner.py:130`（`__new__` + `_initialized` 守卫）
- 实例属性集中初始化: `__init__` 在 `:134-155`，全部按 `instance_id → X` 字典分桶
- 启动: `start()` `:157`；停止: `stop()` `:177`；启动单实例: `_start_instance()` `:283`
- 主循环: `_run_loop()` `:352`，主 except 块在 `:404-413`（当前: log + retry，**不停**）
- 任务退出处理: `_handle_task_done()` `:237-258`（已有逻辑：task 崩溃时 status → `stopped`，与本 spec 要做的 paused 互不干扰）
- 自动下单入口: `_auto_trade()` `:623`，三个真正下单的子方法是 `_auto_open_position` / `_auto_close_position` / `_auto_reverse_position`
- 通知服务: `backend/app/services/notification_service.py:177` 的 `notify_risk_alert(alert_type, message, metrics)` —— 直接复用，**不要新建**
- 模型: `backend/app/models/strategy.py:71-75` `status` 已支持 `paused`；`risk_params: dict` 已是 JSON
- Alembic head: `0009_add_paper_and_contract_settings`（命名规范 `00NN_<topic>.py`，`down_revision: str | None = "00NN-1"`）
- Settings: `backend/app/config.py:19` 起，已有 `telegram_bot_token` / `telegram_chat_id` (`:58-59`)

---

## 2. 变更点（按文件）

### 2.1 `backend/app/models/strategy.py`

在 `last_stopped_at` (`:112-115`) 之后插入：

```python
last_pause_reason: Mapped[str | None] = mapped_column(
    String(64),
    nullable=True,
    default=None,
    comment="自停原因 — auto:consecutive_errors / auto:order_failures / auto:heartbeat_timeout；NULL=用户手动操作",
)
```

不要: 修改现有字段、改 status 枚举、改 workspace_state、加 index、新建表。

### 2.2 `backend/alembic/versions/0010_add_strategy_instance_pause_reason.py`（新建）

完整内容见 §3。

### 2.3 `backend/app/config.py`

在 `Settings` 类内（推荐紧跟 `telegram_chat_id` 之后）插入：

```python
# 自停 / 异常告警 (auto-pause v1)
auto_pause_consecutive_errors: int = 5
auto_pause_consecutive_order_failures: int = 3
auto_pause_heartbeat_multiplier: int = 5
auto_pause_heartbeat_min_seconds: int = 300
auto_pause_watchdog_interval_seconds: int = 30
```

不要: 加 validator、改 BaseSettings 风格、把这些挪到 risk_params。

### 2.4 `backend/.env.example`

追加（保留与 §2.3 同名同值）：

```
# 自停 / 异常告警
AUTO_PAUSE_CONSECUTIVE_ERRORS=5
AUTO_PAUSE_CONSECUTIVE_ORDER_FAILURES=3
AUTO_PAUSE_HEARTBEAT_MULTIPLIER=5
AUTO_PAUSE_HEARTBEAT_MIN_SECONDS=300
AUTO_PAUSE_WATCHDOG_INTERVAL_SECONDS=30
```

### 2.5 `backend/app/core/strategy_runner.py`

#### 2.5.1 `__init__` 增补（紧跟 `:155` `_balance_sync_at` 之后）

```python
# auto-pause v1: 计数器（重启即归零，符合"重启即重置"语义）
self._consecutive_errors: dict[int, int] = {}
self._consecutive_order_failures: dict[int, int] = {}
self._poll_interval: dict[int, int] = {}  # 心跳超时阈值计算用
self._watchdog_task: asyncio.Task | None = None
```

#### 2.5.2 `start()` 末尾启动 watchdog（`:175` 末尾日志之前/之后皆可）

```python
self._watchdog_task = asyncio.create_task(
    self._heartbeat_watchdog_loop(),
    name="strategy-runner-watchdog",
)
```

#### 2.5.3 `stop()` 取消 watchdog 并清理计数器

在 `self._running = False` (`:179`) 之后立即追加：

```python
if self._watchdog_task:
    self._watchdog_task.cancel()
    self._watchdog_task = None
```

在 `:185` 末尾的 `clear()` 块追加：

```python
self._consecutive_errors.clear()
self._consecutive_order_failures.clear()
self._poll_interval.clear()
```

#### 2.5.4 `_run_loop` 改造

A. 在 `interval = int(...)` (`:362`) 之后追加：

```python
self._poll_interval[instance_id] = interval
```

B. 在主 try 块成功路径（`:399` 的 `await asyncio.sleep(interval)` 之前）追加：

```python
self._consecutive_errors[instance_id] = 0
```

C. 整体替换 `except Exception` 块（`:404-413`）为：

```python
except Exception as exc:
    logger.error("[StrategyRunner] 策略 #%d 运行异常: %s", instance_id, exc)
    self._consecutive_errors[instance_id] = (
        self._consecutive_errors.get(instance_id, 0) + 1
    )
    threshold = get_settings().auto_pause_consecutive_errors
    if self._consecutive_errors[instance_id] >= threshold:
        await self._auto_pause(
            instance_id,
            reason="auto:consecutive_errors",
            detail=f"连续 {threshold} 次运行异常，最后异常: {type(exc).__name__}: {exc}",
            metrics={
                "consecutive_errors": self._consecutive_errors[instance_id],
                "last_exc": str(exc),
            },
        )
        break  # 必须 break，否则 task 会继续 retry
    retry_delay = self._calc_retry_delay(exc, interval)
    logger.info(
        "[StrategyRunner] 策略 #%d 异常重试,等待 %.1f 秒",
        instance_id,
        retry_delay,
    )
    await asyncio.sleep(retry_delay)
```

#### 2.5.5 `_auto_trade` / 子方法改造

定义"下单成功" = 订单已成功提交到交易所（即没有抛异常、`signal_status` 不是 `rejected`）。

A. 在 `_auto_open_position` / `_auto_close_position` / `_auto_reverse_position` **每个方法** 的成功落地点追加：

```python
self._consecutive_order_failures[instance_id] = 0
```

B. 在每个子方法**已存在的** 异常捕获块、或写 `signal_status = "rejected"` 的下单失败路径追加（不要新建外层 try/except 包裹；位置以现有 try 块为准）：

```python
self._consecutive_order_failures[instance_id] = (
    self._consecutive_order_failures.get(instance_id, 0) + 1
)
threshold = get_settings().auto_pause_consecutive_order_failures
if self._consecutive_order_failures[instance_id] >= threshold:
    await self._auto_pause(
        instance_id,
        reason="auto:order_failures",
        detail=f"连续 {threshold} 次下单失败",
        metrics={
            "consecutive_order_failures": self._consecutive_order_failures[instance_id],
        },
    )
```

不要: 把"未绑定账户"、"账户不可用"这类配置错误（`_auto_trade` `:642-672`）计入计数器——重试无意义，维持现状只 log。

#### 2.5.6 新增 `_auto_pause`（放在 `_mark_instance_stopped` `:282` 之后）

```python
async def _auto_pause(
    self,
    instance_id: int,
    *,
    reason: str,
    detail: str,
    metrics: dict | None = None,
) -> None:
    """系统判定异常 → status=paused + 推送 risk_alert。

    与 _mark_instance_stopped 的区别:
    - 这里 status=paused, state_json 保留, 用户可恢复
    - _mark_instance_stopped 是 task 硬崩溃, status=stopped
    """
    if not self._session_maker:
        return

    # 1. 取消 task + 清理内存态
    task = self._runners.pop(instance_id, None)
    if task and not task.done():
        task.cancel()
    self._strategies.pop(instance_id, None)
    self._consecutive_errors.pop(instance_id, None)
    self._consecutive_order_failures.pop(instance_id, None)
    self._poll_interval.pop(instance_id, None)

    # 2. 写 DB
    instance_name = "未知策略"
    try:
        async with self._session_maker() as session:
            result = await session.execute(
                select(StrategyInstance).where(StrategyInstance.id == instance_id)
            )
            inst = result.scalar_one_or_none()
            if not inst:
                return
            instance_name = inst.name
            inst.status = "paused"
            inst.last_pause_reason = reason
            inst.last_stopped_at = datetime.now(UTC)
            await session.commit()
    except Exception as exc:
        logger.error(
            "[StrategyRunner] 自停状态写库失败 #%d: %s", instance_id, exc
        )

    logger.warning(
        "[StrategyRunner] 策略 #%d (%s) 已自动暂停: reason=%s detail=%s",
        instance_id, instance_name, reason, detail,
    )

    # 3. 推送告警（失败不抛）
    try:
        from app.services.notification_service import notify_risk_alert

        await notify_risk_alert(
            alert_type="策略自停",
            message=f'策略 "{instance_name}" (#{instance_id}) {detail}',
            metrics={"reason": reason, "instance_id": instance_id, **(metrics or {})},
        )
    except Exception as exc:
        logger.warning("[StrategyRunner] 自停告警推送失败 #%d: %s", instance_id, exc)
```

`notify_risk_alert` 是 `notification_service` 模块级便捷函数（位于 `notification_service.py:275` 的单例外层），与 `strategy_runner.py:567` 现有 `notify_signal` 用法一致——保持 lazy import，**不要**改成顶部 import。

#### 2.5.7 新增 `_heartbeat_watchdog_loop`（放在 `_auto_pause` 之后）

```python
async def _heartbeat_watchdog_loop(self) -> None:
    """周期扫描 running 实例，检测 last_run_at 过旧。

    超时阈值 = max(poll_interval × multiplier, min_seconds)
    """
    settings = get_settings()
    while self._running:
        try:
            await asyncio.sleep(settings.auto_pause_watchdog_interval_seconds)
            if not self._running or not self._session_maker:
                continue

            async with self._session_maker() as session:
                result = await session.execute(
                    select(StrategyInstance).where(
                        StrategyInstance.status == "running"
                    )
                )
                instances = list(result.scalars().all())

            now = datetime.now(UTC)
            for inst in instances:
                if inst.id not in self._runners:
                    continue  # task 已不存在，由 _handle_task_done 处理
                if inst.last_run_at is None:
                    continue  # 首次启动，未跑完一圈，给它机会

                interval = self._poll_interval.get(inst.id, 60)
                threshold_seconds = max(
                    interval * settings.auto_pause_heartbeat_multiplier,
                    settings.auto_pause_heartbeat_min_seconds,
                )
                age_seconds = (now - inst.last_run_at).total_seconds()
                if age_seconds > threshold_seconds:
                    await self._auto_pause(
                        inst.id,
                        reason="auto:heartbeat_timeout",
                        detail=f"心跳超时 {age_seconds:.0f}s > 阈值 {threshold_seconds}s",
                        metrics={
                            "age_seconds": int(age_seconds),
                            "threshold_seconds": threshold_seconds,
                        },
                    )
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("[StrategyRunner] watchdog 异常: %s", exc)
```

#### 2.5.8 import 检查

文件顶部 import 区若没有 `from app.config import get_settings`，补一行；`notification_service` 保持 lazy import（避免循环）。

---

## 3. 完整 migration 脚本

`backend/alembic/versions/0010_add_strategy_instance_pause_reason.py`：

```python
"""add strategy_instances.last_pause_reason

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-09 00:00:00.000000

auto-pause v1: 记录策略自停原因，区分用户操作（NULL）与系统判定（auto:*）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "strategy_instances",
        sa.Column(
            "last_pause_reason",
            sa.String(length=64),
            nullable=True,
            comment="自停原因 — auto:consecutive_errors / auto:order_failures / auto:heartbeat_timeout；NULL=用户手动操作",
        ),
    )


def downgrade() -> None:
    op.drop_column("strategy_instances", "last_pause_reason")
```

不要: 加 server_default、加 index、写 op.execute 数据回填。

---

## 4. 测试用例

文件: `backend/tests/test_strategy_runner_auto_pause.py`（新建）

每个测试都按"准备 → 触发 → 断言 + reset 单例状态"模式。所有 mock 走 `monkeypatch` + `AsyncMock`。

### 4.1 测试列表（codex 必须全部实现并通过）

| 测试名 | 输入 | 期望 |
|---|---|---|
| `test_consecutive_errors_threshold_triggers_pause` | mock `_run_loop` 内异常连续抛 5 次 | `_auto_pause` 被调用 1 次，`reason="auto:consecutive_errors"` |
| `test_consecutive_errors_reset_on_success` | 异常 4 次 → 成功 1 次 → 异常 1 次 | 第 6 次时计数器为 1，不触发 |
| `test_order_failures_threshold_triggers_pause` | mock `_auto_open_position` 失败 3 次 | `_auto_pause` 被调用 1 次，`reason="auto:order_failures"` |
| `test_order_failures_reset_on_success` | 失败 2 次 → 成功 1 次 → 失败 1 次 | 计数器为 1，不触发 |
| `test_heartbeat_watchdog_triggers_pause_when_stale` | mock `last_run_at = now - 11min`，threshold=300s | `_auto_pause` 被调用 1 次，`reason="auto:heartbeat_timeout"` |
| `test_heartbeat_watchdog_skips_when_no_last_run_at` | `last_run_at=None` | `_auto_pause` 不被调用 |
| `test_auto_pause_writes_paused_status_and_reason` | 直接调 `_auto_pause(42, reason="auto:x", detail="d")` | DB 内 `status="paused"`, `last_pause_reason="auto:x"`，`notify_risk_alert` 被调用一次 |
| `test_auto_pause_swallows_notification_failure` | mock `notify_risk_alert` 抛异常 | `_auto_pause` 不抛，仍写库成功 |

### 4.2 测试骨架（fixture 部分必须严格按此）

```python
import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.strategy_runner import StrategyRunner


@pytest.fixture(autouse=True)
def reset_runner_singleton():
    """每个测试前重置单例内部状态"""
    r = StrategyRunner()
    r._consecutive_errors.clear()
    r._consecutive_order_failures.clear()
    r._poll_interval.clear()
    r._runners.clear()
    r._strategies.clear()
    yield r
    r._consecutive_errors.clear()
    r._consecutive_order_failures.clear()


@pytest.fixture
def fake_settings(monkeypatch):
    """注入测试专用阈值 — 让计数器更快触发"""
    settings = MagicMock(
        auto_pause_consecutive_errors=5,
        auto_pause_consecutive_order_failures=3,
        auto_pause_heartbeat_multiplier=5,
        auto_pause_heartbeat_min_seconds=300,
        auto_pause_watchdog_interval_seconds=1,
    )
    monkeypatch.setattr(
        "app.core.strategy_runner.get_settings", lambda: settings
    )
    return settings
```

### 4.3 重点测试样例

```python
@pytest.mark.asyncio
async def test_auto_pause_writes_paused_status_and_reason(
    reset_runner_singleton, fake_settings, monkeypatch
):
    """直接调用 _auto_pause 应：cancel task + 写 DB(paused, reason) + 推送告警"""
    runner = reset_runner_singleton

    # mock session_maker 返回一个含 inst.id=42 的实例
    fake_inst = MagicMock(id=42, name="测试策略")
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_inst))
    )
    fake_session.commit = AsyncMock()
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)
    runner._session_maker = MagicMock(return_value=fake_session_cm)

    # mock notify_risk_alert（patch 模块级便捷函数）
    notify_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(
        "app.services.notification_service.notify_risk_alert",
        notify_mock,
    )

    await runner._auto_pause(
        42, reason="auto:consecutive_errors", detail="测试细节", metrics={"k": "v"}
    )

    # 断言: DB 字段被写
    assert fake_inst.status == "paused"
    assert fake_inst.last_pause_reason == "auto:consecutive_errors"
    fake_session.commit.assert_awaited_once()

    # 断言: 告警被发
    notify_mock.assert_awaited_once()
    call_kwargs = notify_mock.call_args.kwargs
    assert call_kwargs["alert_type"] == "策略自停"
    assert "测试策略" in call_kwargs["message"]
    assert call_kwargs["metrics"]["reason"] == "auto:consecutive_errors"
    assert call_kwargs["metrics"]["instance_id"] == 42
    assert call_kwargs["metrics"]["k"] == "v"
```

不要: 启动真正的 watchdog `asyncio.create_task`；不要使用真实 DB；不要 sleep 等真实时间。

---

## 5. 验收标准

执行下列命令应**全部通过**：

```bash
docker compose run --rm backend python -m black --check .
docker compose run --rm backend ruff check .
docker compose run --rm backend pytest backend/tests/test_strategy_runner_auto_pause.py -v
docker compose run --rm backend pytest backend/tests/ -x   # 完整测试套件不破坏
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend alembic downgrade -1
docker compose run --rm backend alembic upgrade head
```

代码 grep 验证：

```bash
# 三个 reason 字面量必须存在
grep -c "auto:consecutive_errors\|auto:order_failures\|auto:heartbeat_timeout" \
  backend/app/core/strategy_runner.py
# 期望: ≥ 3

# 关键方法名必须存在
grep -n "async def _auto_pause\|async def _heartbeat_watchdog_loop" \
  backend/app/core/strategy_runner.py
# 期望: 2 行

# model 字段
grep -n "last_pause_reason" backend/app/models/strategy.py
# 期望: 1 行
```

---

## 6. 反范式（明确不要做）

1. 不要做账户回撤检测、PnL 异常突变检测——v1 不在范围
2. 不要在前端加每策略阈值配置面板——YAGNI
3. 不要把 `_auto_pause` 暴露成 API endpoint 或 service 层
4. 不要把异常计数器写到数据库——重启即归零是**预期**行为
5. 不要给 paused 状态加自动恢复 / 自动 retry——必须人工确认
6. 不要在告警里加 emoji 解释、操作建议、stack trace
7. 不要把 watchdog 做成 cron / BackgroundTasks——asyncio.Task 已足够
8. 不要修改 `_handle_task_done` (`:237`) 改 stopped 的逻辑——硬崩溃和软自停语义不同
9. 不要新建 `notify_auto_pause` 之类的专用通知函数——直接复用 `notify_risk_alert`
10. 不要给 `last_pause_reason` 设 default、index、enum
11. 不要顺手"清理"附近你看着不爽的代码、不要重构邻近函数、不要"改进"现有注释
12. 不要把 settings 字段挪到 `risk_params` JSON 字段里
13. 不要在 `_auto_trade` 配置错误路径（未绑定账户/账户不可用）累计 `_consecutive_order_failures`

---

## 7. Commit 分片建议（按顺序交付，每片可独立测试）

| # | 内容 | 验证 |
|---|---|---|
| 1 | model 加字段 + migration | `alembic upgrade head` && `alembic downgrade -1` 都过 |
| 2 | config.py + .env.example 加 5 字段 | `python -c "from app.config import get_settings; print(get_settings().auto_pause_consecutive_errors)"` 输出 5 |
| 3 | 加 `_auto_pause` 方法 + 写 `test_auto_pause_writes_*` | 单测过 |
| 4 | `__init__` 加 `_consecutive_errors` + `_run_loop` 改造 + 相关测试 | 单测过 |
| 5 | `__init__` 加 `_consecutive_order_failures` + `_auto_trade` 子方法改造 + 相关测试 | 单测过 |
| 6 | 加 `_watchdog_task` + watchdog 方法 + start/stop 改造 + 相关测试 | §5 全部验收命令通过 |

每个 commit 之间必须保证 `pytest backend/tests/ -x` 不跑挂；最后一个 commit 完成后跑 §5 完整验收。

---

## 8. 不在本次 spec 内（后续单独立项）

- 账户级回撤阈值自停（业务规则、PnL 口径选型）
- PnL 异常突变检测
- UI 上"已自停"红色横幅 + 一键恢复按钮（前端工作）
- 自停事件写入 audit_log
- 自停后冷却期（防恢复后立即再次触发）
