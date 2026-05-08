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
    r._running = False
    r._session_maker = None
    r._watchdog_task = None
    r._consecutive_errors.clear()
    r._consecutive_order_failures.clear()
    r._poll_interval.clear()
    r._runners.clear()
    r._strategies.clear()
    r._last_signal_at.clear()
    yield r
    r._running = False
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
    monkeypatch.setattr("app.core.strategy_runner.get_settings", lambda: settings)
    return settings


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
async def test_order_failures_reset_on_success(
    reset_runner_singleton, fake_settings, monkeypatch
):
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
    fake_session.commit.assert_awaited_once()

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
    fake_session.commit.assert_awaited_once()
