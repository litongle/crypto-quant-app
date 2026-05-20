import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.strategy_engine import Signal, StrategyConfig
from app.core.strategy_runner import StrategyRunner


@pytest.fixture(autouse=True)
def reset_runner_singleton():
    """每个测试前重置单例内部状态"""
    r = StrategyRunner()
    r._auto_pause = StrategyRunner._auto_pause.__get__(r, StrategyRunner)
    r._running = False
    r._session_maker = None
    r._watchdog_task = None
    r._consecutive_errors.clear()
    r._consecutive_order_failures.clear()
    r._poll_interval.clear()
    r._runners.clear()
    r._strategies.clear()
    r._last_signal_at.clear()
    r._auto_paused_pending.clear()
    yield r
    r._auto_pause = StrategyRunner._auto_pause.__get__(r, StrategyRunner)
    r._running = False
    r._consecutive_errors.clear()
    r._consecutive_order_failures.clear()
    r._auto_paused_pending.clear()


@pytest.fixture
def fake_settings(monkeypatch):
    """注入测试专用阈值 — 让计数器更快触发"""
    config = {
        "consecutive_errors": 5,
        "consecutive_order_failures": 3,
        "heartbeat_multiplier": 5,
        "heartbeat_min_seconds": 300,
        "watchdog_interval_seconds": 1,
    }

    async def fake_read(self):
        return config

    monkeypatch.setattr(StrategyRunner, "_read_auto_pause_config", fake_read)
    return config


def _make_config(**params) -> StrategyConfig:
    return StrategyConfig(
        symbol="BTCUSDT",
        exchange="binance",
        direction="both",
        params=params,
        risk_params={},
    )


def _make_signal(action: str = "buy") -> Signal:
    return Signal(
        action=action,
        confidence=0.9,
        reason="test",
        entry_price=Decimal("100"),
    )


@pytest.mark.asyncio
async def test_consecutive_errors_threshold_triggers_pause(
    reset_runner_singleton, fake_settings, monkeypatch
):
    runner = reset_runner_singleton
    runner._running = True
    runner._fetch_klines_cached = AsyncMock(side_effect=RuntimeError("boom"))
    runner._auto_pause = AsyncMock()
    monkeypatch.setattr("app.core.strategy_runner.asyncio.sleep", AsyncMock())

    await runner._run_loop(1, MagicMock(), _make_config(interval=1))

    runner._auto_pause.assert_awaited_once()
    assert runner._auto_pause.call_args.kwargs["reason"] == "auto:consecutive_errors"


@pytest.mark.asyncio
async def test_consecutive_errors_reset_on_success(
    reset_runner_singleton, fake_settings, monkeypatch
):
    runner = reset_runner_singleton
    runner._running = True
    strategy = MagicMock()
    strategy.analyze = AsyncMock(return_value=None)
    runner._handle_signal = AsyncMock()
    runner._update_position_prices = AsyncMock()
    runner._update_last_run_and_state = AsyncMock()
    runner._auto_pause = AsyncMock()
    monkeypatch.setattr("app.core.strategy_runner.asyncio.sleep", AsyncMock())

    step = {"value": 0}

    async def fake_fetch(*args, **kwargs):
        step["value"] += 1
        if step["value"] <= 4:
            raise RuntimeError("boom")
        if step["value"] == 5:
            return [{"close": 100}]
        if step["value"] == 6:
            runner._running = False
            raise RuntimeError("boom")
        return []

    runner._fetch_klines_cached = AsyncMock(side_effect=fake_fetch)

    await runner._run_loop(1, strategy, _make_config(interval=1))

    runner._auto_pause.assert_not_awaited()
    assert runner._consecutive_errors[1] == 1


@pytest.mark.asyncio
async def test_order_failures_threshold_triggers_pause(
    reset_runner_singleton, fake_settings, monkeypatch
):
    runner = reset_runner_singleton
    runner._update_signal_status = AsyncMock()
    runner._auto_pause = AsyncMock()
    runner._get_symbol_min_qty = AsyncMock(return_value=Decimal("0.001"))
    runner._calculate_order_quantity = MagicMock(return_value=Decimal("1"))

    class FailingOrderService:
        def __init__(self, session):
            self.order_repo = MagicMock(delete=AsyncMock())

        async def create_order(self, **kwargs):
            return MagicMock(id=123)

        async def submit_order(self, order_id, user_id):
            raise RuntimeError("submit failed")

    monkeypatch.setattr("app.services.order_service.OrderService", FailingOrderService)

    session = MagicMock(commit=AsyncMock())
    account = MagicMock(id=1, balance=Decimal("1000"))

    for _ in range(3):
        with pytest.raises(RuntimeError, match="submit failed"):
            await runner._auto_open_position(
                session=session,
                instance_id=1,
                account=account,
                config=_make_config(),
                user_id=7,
                signal=_make_signal(),
                signal_id=9,
            )

    runner._auto_pause.assert_awaited_once()
    assert runner._auto_pause.call_args.kwargs["reason"] == "auto:order_failures"


@pytest.mark.asyncio
async def test_order_failures_reset_on_success(reset_runner_singleton, fake_settings, monkeypatch):
    runner = reset_runner_singleton
    runner._update_signal_status = AsyncMock()
    runner._auto_pause = AsyncMock()
    runner._get_symbol_min_qty = AsyncMock(return_value=Decimal("0.001"))
    runner._calculate_order_quantity = MagicMock(return_value=Decimal("1"))

    attempts = {"count": 0}

    class FlakyOrderService:
        def __init__(self, session):
            self.order_repo = MagicMock(delete=AsyncMock())

        async def create_order(self, **kwargs):
            return MagicMock(id=attempts["count"] + 1)

        async def submit_order(self, order_id, user_id):
            attempts["count"] += 1
            if attempts["count"] in {1, 2, 4}:
                raise RuntimeError(f"submit failed {attempts['count']}")

    monkeypatch.setattr("app.services.order_service.OrderService", FlakyOrderService)

    session = MagicMock(commit=AsyncMock())
    account = MagicMock(id=1, balance=Decimal("1000"))

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await runner._auto_open_position(
                session=session,
                instance_id=1,
                account=account,
                config=_make_config(),
                user_id=7,
                signal=_make_signal(),
                signal_id=9,
            )

    assert await runner._auto_open_position(
        session=session,
        instance_id=1,
        account=account,
        config=_make_config(),
        user_id=7,
        signal=_make_signal(),
        signal_id=9,
    )

    with pytest.raises(RuntimeError):
        await runner._auto_open_position(
            session=session,
            instance_id=1,
            account=account,
            config=_make_config(),
            user_id=7,
            signal=_make_signal(),
            signal_id=9,
        )

    runner._auto_pause.assert_not_awaited()
    assert runner._consecutive_order_failures[1] == 1


@pytest.mark.asyncio
async def test_heartbeat_watchdog_triggers_pause_when_stale(
    reset_runner_singleton, fake_settings, monkeypatch
):
    runner = reset_runner_singleton
    runner._running = True
    runner._runners[1] = MagicMock()
    runner._poll_interval[1] = 60

    stale_inst = MagicMock()
    stale_inst.id = 1
    stale_inst.status = "running"
    stale_inst.last_run_at = datetime.now(UTC) - timedelta(minutes=11)
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = [stale_inst]
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=fake_result)
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)
    runner._session_maker = MagicMock(return_value=fake_session_cm)

    async def fake_auto_pause(*args, **kwargs):
        runner._running = False

    runner._auto_pause = AsyncMock(side_effect=fake_auto_pause)
    monkeypatch.setattr("app.core.strategy_runner.asyncio.sleep", AsyncMock())

    await runner._heartbeat_watchdog_loop()

    runner._auto_pause.assert_awaited_once()
    assert runner._auto_pause.call_args.kwargs["reason"] == "auto:heartbeat_timeout"


@pytest.mark.asyncio
async def test_heartbeat_watchdog_skips_when_no_last_run_at(
    reset_runner_singleton, fake_settings, monkeypatch
):
    runner = reset_runner_singleton
    runner._running = True
    runner._runners[1] = MagicMock()

    inst = MagicMock()
    inst.id = 1
    inst.status = "running"
    inst.last_run_at = None
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = [inst]
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=fake_result)
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)
    runner._session_maker = MagicMock(return_value=fake_session_cm)
    runner._auto_pause = AsyncMock()

    sleep_calls = {"count": 0}

    async def fake_sleep(_seconds):
        sleep_calls["count"] += 1
        if sleep_calls["count"] > 1:
            runner._running = False

    monkeypatch.setattr("app.core.strategy_runner.asyncio.sleep", fake_sleep)

    await runner._heartbeat_watchdog_loop()

    runner._auto_pause.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_pause_writes_paused_status_and_reason(
    reset_runner_singleton, fake_settings, monkeypatch
):
    """直接调用 _auto_pause 应：cancel task + 写 DB(paused, reason) + 推送告警"""
    runner = reset_runner_singleton

    fake_inst = MagicMock()
    fake_inst.id = 42
    fake_inst.name = "测试策略"
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_inst))
    )
    fake_session.commit = AsyncMock()
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)
    runner._session_maker = MagicMock(return_value=fake_session_cm)

    notify_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(
        "app.services.notification_service.notify_risk_alert",
        notify_mock,
    )

    await runner._auto_pause(
        42, reason="auto:consecutive_errors", detail="测试细节", metrics={"k": "v"}
    )

    assert fake_inst.status == "paused"
    assert fake_inst.last_pause_reason == "auto:consecutive_errors"
    assert fake_session.commit.await_count >= 1

    notify_mock.assert_awaited_once()
    call_kwargs = notify_mock.call_args.kwargs
    assert call_kwargs["alert_type"] == "策略自停"
    assert "测试策略" in call_kwargs["message"]
    assert call_kwargs["metrics"]["reason"] == "auto:consecutive_errors"
    assert call_kwargs["metrics"]["instance_id"] == 42
    assert call_kwargs["metrics"]["k"] == "v"


@pytest.mark.asyncio
async def test_auto_pause_swallows_notification_failure(
    reset_runner_singleton, fake_settings, monkeypatch
):
    runner = reset_runner_singleton

    fake_inst = MagicMock()
    fake_inst.id = 42
    fake_inst.name = "测试策略"
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_inst))
    )
    fake_session.commit = AsyncMock()
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)
    runner._session_maker = MagicMock(return_value=fake_session_cm)

    notify_mock = AsyncMock(side_effect=RuntimeError("notify failed"))
    monkeypatch.setattr(
        "app.services.notification_service.notify_risk_alert",
        notify_mock,
    )

    await runner._auto_pause(42, reason="auto:x", detail="d")

    assert fake_inst.status == "paused"
    assert fake_inst.last_pause_reason == "auto:x"
    assert fake_session.commit.await_count >= 1


@pytest.mark.asyncio
async def test_mark_instance_stopped_pushes_crash_alert(
    reset_runner_singleton, fake_settings, monkeypatch
):
    """task 硬崩溃 → _mark_instance_stopped 应写 stopped + 推送 alert_type='策略崩溃'。

    与 _auto_pause（策略自停）区分：硬崩溃是「没拦住」的状态，必须有独立告警类型，
    不能跟系统主动暂停混在一起。
    """
    runner = reset_runner_singleton

    fake_inst = MagicMock()
    fake_inst.id = 99
    fake_inst.name = "崩溃测试"
    fake_inst.status = "running"
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_inst))
    )
    fake_session.commit = AsyncMock()
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)
    runner._session_maker = MagicMock(return_value=fake_session_cm)

    notify_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(
        "app.services.notification_service.notify_risk_alert",
        notify_mock,
    )

    await runner._mark_instance_stopped(99, "RuntimeError: 模拟崩溃")

    assert fake_inst.status == "stopped"
    assert fake_session.commit.await_count >= 1

    notify_mock.assert_awaited_once()
    call_kwargs = notify_mock.call_args.kwargs
    assert call_kwargs["alert_type"] == "策略崩溃"
    assert "崩溃测试" in call_kwargs["message"]
    assert "RuntimeError" in call_kwargs["message"]
    assert call_kwargs["metrics"]["reason"] == "task_crashed"
    assert call_kwargs["metrics"]["instance_id"] == 99


@pytest.mark.asyncio
async def test_mark_instance_stopped_no_alert_when_already_stopped(
    reset_runner_singleton, fake_settings, monkeypatch
):
    """status 已经不是 running 时（重复调用）不应重复告警。"""
    runner = reset_runner_singleton

    fake_inst = MagicMock()
    fake_inst.id = 99
    fake_inst.status = "stopped"
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_inst))
    )
    fake_session.commit = AsyncMock()
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)
    runner._session_maker = MagicMock(return_value=fake_session_cm)

    notify_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(
        "app.services.notification_service.notify_risk_alert",
        notify_mock,
    )

    await runner._mark_instance_stopped(99, "重复调用")

    notify_mock.assert_not_awaited()
    fake_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_task_done_skips_mark_when_auto_pause_pending(
    reset_runner_singleton,
):
    """回归 — watchdog 触发 _auto_pause 的瞬间,task 因 cancel 提前 done。
    _handle_task_done 必须看到 _auto_paused_pending 标记后跳过 _mark_instance_stopped,
    否则 stopped 会覆盖 paused、双告警齐发(策略自停 + 策略崩溃)。
    """
    runner = reset_runner_singleton
    runner._running = True
    runner._auto_paused_pending.add(99)

    task = MagicMock(spec=asyncio.Task)
    task.cancelled.return_value = False
    task.exception.return_value = None

    created_tasks: list = []
    original_create_task = asyncio.create_task

    def capture(coro, **kwargs):
        created_tasks.append(coro)
        coro.close()
        return MagicMock()

    import app.core.strategy_runner as runner_mod

    runner_mod.asyncio.create_task = capture
    try:
        runner._handle_task_done(99, task)
    finally:
        runner_mod.asyncio.create_task = original_create_task

    # 关键断言:没有触发 _mark_instance_stopped 协程
    assert created_tasks == []


@pytest.mark.asyncio
async def test_auto_pause_manages_pending_marker(
    reset_runner_singleton, fake_settings, monkeypatch
):
    """_auto_pause 进入即加 _auto_paused_pending,完成后清掉。"""
    runner = reset_runner_singleton

    fake_inst = MagicMock()
    fake_inst.id = 77
    fake_inst.name = "竞态测试"
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_inst))
    )
    fake_session.commit = AsyncMock()
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)
    runner._session_maker = MagicMock(return_value=fake_session_cm)

    captured: dict[str, bool] = {}

    async def capture_pending(*args, **kwargs):
        captured["in_pending_during_notify"] = 77 in runner._auto_paused_pending
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.notification_service.notify_risk_alert",
        capture_pending,
    )

    assert 77 not in runner._auto_paused_pending
    await runner._auto_pause(77, reason="auto:x", detail="d")

    assert captured["in_pending_during_notify"] is True
    assert 77 not in runner._auto_paused_pending


@pytest.mark.asyncio
async def test_run_loop_propagates_cancellation(reset_runner_singleton, fake_settings, monkeypatch):
    """回归 — _run_loop 被外部 cancel 时,CancelledError 必须传播到 task,
    否则 task.cancelled() == False 会让 done_callback 误判为崩溃。
    """
    runner = reset_runner_singleton
    runner._running = True

    started = asyncio.Event()

    async def fake_fetch(*args, **kwargs):
        started.set()
        await asyncio.sleep(60)  # 阻塞直到被 cancel
        return []

    runner._fetch_klines_cached = fake_fetch
    runner._handle_signal = AsyncMock()
    runner._update_position_prices = AsyncMock()
    runner._update_last_run_and_state = AsyncMock()

    task = asyncio.create_task(
        runner._run_loop(
            1, MagicMock(analyze=AsyncMock(return_value=None)), _make_config(interval=1)
        )
    )
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert task.cancelled() is True


@pytest.mark.asyncio
async def test_mark_instance_stopped_swallows_notification_failure(
    reset_runner_singleton, fake_settings, monkeypatch
):
    """notify 失败不影响 status 落库。"""
    runner = reset_runner_singleton

    fake_inst = MagicMock()
    fake_inst.id = 99
    fake_inst.name = "崩溃测试"
    fake_inst.status = "running"
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_inst))
    )
    fake_session.commit = AsyncMock()
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)
    runner._session_maker = MagicMock(return_value=fake_session_cm)

    notify_mock = AsyncMock(side_effect=RuntimeError("notify failed"))
    monkeypatch.setattr(
        "app.services.notification_service.notify_risk_alert",
        notify_mock,
    )

    await runner._mark_instance_stopped(99, "RuntimeError: 崩溃")

    assert fake_inst.status == "stopped"
    assert fake_session.commit.await_count >= 1


# ==================== 仓位对账 (DB ↔ 交易所) ====================


def _make_running_instance(inst_id: int, *, account_id: int = 7, symbol: str = "ETHUSDT.P"):
    inst = MagicMock()
    inst.id = inst_id
    inst.account_id = account_id
    inst.symbol = symbol
    inst.status = "running"
    return inst


def _make_db_position(*, side: str, qty: str):
    p = MagicMock()
    p.side = side
    p.quantity = Decimal(qty)
    p.status = "open"
    return p


def _make_exchange_position(*, symbol: str, side: str, qty: str):
    p = MagicMock()
    p.symbol = symbol
    p.side = side
    p.quantity = Decimal(qty)
    return p


def _stub_reconcile_session(
    runner, *, exchange_account, db_positions: list, exchange_positions: list, monkeypatch
):
    """让 _reconcile_positions_for_running 看到的 session.execute 返回固定数据。

    调用次序固定：先 select(ExchangeAccount)，再 select(Position)。
    """
    calls = {"i": 0}

    async def fake_execute(stmt):
        idx = calls["i"]
        calls["i"] += 1
        result = MagicMock()
        if idx == 0:
            result.scalar_one_or_none = MagicMock(return_value=exchange_account)
        else:
            result.scalars.return_value.all.return_value = db_positions
        return result

    fake_session = AsyncMock()
    fake_session.execute = fake_execute
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)
    runner._session_maker = MagicMock(return_value=fake_session_cm)

    adapter = MagicMock()
    adapter.get_positions = AsyncMock(return_value=exchange_positions)
    adapter.close = AsyncMock()
    monkeypatch.setattr(
        "app.core.exchange_adapter.get_exchange_adapter",
        MagicMock(return_value=adapter),
    )
    return adapter


def test_normalize_okx_symbol_to_compact():
    f = StrategyRunner._normalize_okx_symbol_to_compact
    assert f("ETH-USDT-SWAP") == "ETHUSDT"
    assert f("BTC-USDT") == "BTCUSDT"
    assert f("ETHUSDT") == "ETHUSDT"
    assert f("eth-usdt-swap") == "ETHUSDT"
    assert f("") == ""


@pytest.mark.asyncio
async def test_reconcile_no_drift_does_not_pause(
    reset_runner_singleton, fake_settings, monkeypatch
):
    runner = reset_runner_singleton
    runner._running = True
    runner._runners[1] = MagicMock()

    account = MagicMock()
    account.exchange = "okx"
    account.get_api_key = MagicMock(return_value="k")
    account.get_secret_key = MagicMock(return_value="s")
    account.get_passphrase = MagicMock(return_value="p")
    account.is_demo = True

    _stub_reconcile_session(
        runner,
        exchange_account=account,
        db_positions=[_make_db_position(side="short", qty="2.5")],
        exchange_positions=[
            _make_exchange_position(symbol="ETH-USDT-SWAP", side="short", qty="2.5"),
        ],
        monkeypatch=monkeypatch,
    )
    runner._auto_pause = AsyncMock()

    await runner._reconcile_positions_for_running([_make_running_instance(1)])

    runner._auto_pause.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_drift_triggers_state_drift_pause(
    reset_runner_singleton, fake_settings, monkeypatch
):
    """DB 净仓 0（漂移后丢失） vs OKX 净仓 -2.5（仍持空） → state_drift。"""
    runner = reset_runner_singleton
    runner._running = True
    runner._runners[1] = MagicMock()

    account = MagicMock()
    account.exchange = "okx"
    account.get_api_key = MagicMock(return_value="k")
    account.get_secret_key = MagicMock(return_value="s")
    account.get_passphrase = MagicMock(return_value="p")
    account.is_demo = True

    _stub_reconcile_session(
        runner,
        exchange_account=account,
        db_positions=[],  # DB 没仓 — 漂移
        exchange_positions=[
            _make_exchange_position(symbol="ETH-USDT-SWAP", side="short", qty="2.5"),
        ],
        monkeypatch=monkeypatch,
    )
    runner._auto_pause = AsyncMock()

    await runner._reconcile_positions_for_running([_make_running_instance(1)])

    runner._auto_pause.assert_awaited_once()
    kwargs = runner._auto_pause.call_args.kwargs
    assert kwargs["reason"] == "auto:state_drift"
    assert kwargs["metrics"]["symbol"] == "ETHUSDT"
    assert kwargs["metrics"]["db_net_qty"] == "0"
    assert kwargs["metrics"]["exchange_net_qty"] == "-2.5"


@pytest.mark.asyncio
async def test_reconcile_adapter_error_does_not_pause(
    reset_runner_singleton, fake_settings, monkeypatch
):
    """拉交易所持仓失败不应误判为漂移（网络抖动容错）。"""
    runner = reset_runner_singleton
    runner._running = True
    runner._runners[1] = MagicMock()

    account = MagicMock()
    account.exchange = "okx"
    account.get_api_key = MagicMock(return_value="k")
    account.get_secret_key = MagicMock(return_value="s")
    account.get_passphrase = MagicMock(return_value="p")
    account.is_demo = True

    async def fake_execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=account)
        return result

    fake_session = AsyncMock()
    fake_session.execute = fake_execute
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)
    runner._session_maker = MagicMock(return_value=fake_session_cm)

    adapter = MagicMock()
    adapter.get_positions = AsyncMock(side_effect=RuntimeError("network"))
    adapter.close = AsyncMock()
    monkeypatch.setattr(
        "app.core.exchange_adapter.get_exchange_adapter",
        MagicMock(return_value=adapter),
    )

    runner._auto_pause = AsyncMock()
    await runner._reconcile_positions_for_running([_make_running_instance(1)])

    runner._auto_pause.assert_not_awaited()
