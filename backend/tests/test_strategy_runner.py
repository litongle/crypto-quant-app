"""
策略运行器单元测试 — select_position_to_close、数量计算、生命周期管理
"""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.strategy_engine import Signal, StrategyConfig
from app.core.strategy_runner import StrategyRunner, select_position_to_close


# ==================== Fixtures ====================

@pytest.fixture
def runner():
    """每个测试都拿到一个干净的 StrategyRunner（绕过单例）"""
    StrategyRunner._instance = None
    r = StrategyRunner()
    yield r
    StrategyRunner._instance = None


def _pos(id_, instance_id, side):
    p = MagicMock()
    p.id = id_
    p.strategy_instance_id = instance_id
    p.side = side
    return p


_UNSET = object()


def _make_session_mock(instances=_UNSET, scalar_result=_UNSET):
    """返回可用于 async with session_maker() 的 mock。"""
    result_mock = MagicMock()
    if instances is not _UNSET:
        result_mock.scalars.return_value.all.return_value = instances
    if scalar_result is not _UNSET:
        result_mock.scalar_one_or_none.return_value = scalar_result

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session, lambda: session


# ==================== select_position_to_close ====================

class TestSelectPositionToClose:
    def test_empty_list_returns_none(self):
        assert select_position_to_close([], 1, None) is None

    def test_single_position_returned(self):
        pos = _pos(1, 1, "long")
        assert select_position_to_close([pos], 1, None) is pos

    def test_same_instance_preferred_over_other(self):
        other = _pos(1, 99, "long")
        own = _pos(2, 1, "long")
        assert select_position_to_close([other, own], 1, None) is own

    def test_direction_filter_long(self):
        long_pos = _pos(1, 1, "long")
        short_pos = _pos(2, 1, "short")
        assert select_position_to_close([long_pos, short_pos], 1, "long") is long_pos

    def test_direction_filter_short(self):
        long_pos = _pos(1, 1, "long")
        short_pos = _pos(2, 1, "short")
        assert select_position_to_close([long_pos, short_pos], 1, "short") is short_pos

    def test_direction_filter_fallback_when_no_match(self):
        long_pos = _pos(1, 1, "long")
        # only long available, asked for short → fall back to first candidate
        result = select_position_to_close([long_pos], 1, "short")
        assert result is long_pos

    def test_no_direction_returns_first_candidate(self):
        pos1 = _pos(1, 1, "long")
        pos2 = _pos(2, 1, "short")
        assert select_position_to_close([pos1, pos2], 1, None) is pos1

    def test_no_same_instance_falls_back_to_all(self):
        a = _pos(1, 99, "long")
        b = _pos(2, 98, "short")
        assert select_position_to_close([a, b], 1, None) is a


# ==================== _calculate_order_quantity ====================

class TestCalculateOrderQuantity:
    def setup_method(self):
        StrategyRunner._instance = None
        self.runner = StrategyRunner()

    def teardown_method(self):
        StrategyRunner._instance = None

    def test_none_entry_price_returns_zero(self):
        assert self.runner._calculate_order_quantity(
            Decimal("10000"), None, "BTCUSDT", "buy"
        ) == Decimal("0")

    def test_zero_entry_price_returns_zero(self):
        assert self.runner._calculate_order_quantity(
            Decimal("10000"), Decimal("0"), "BTCUSDT", "buy"
        ) == Decimal("0")

    def test_btc_above_min_returns_calculated_qty(self):
        # balance=10000, price=50000, 30% → invest=3000, qty=0.06 > 0.001
        qty = self.runner._calculate_order_quantity(
            Decimal("10000"), Decimal("50000"), "BTCUSDT", "buy"
        )
        assert qty == Decimal("3000") / Decimal("50000")

    def test_btc_below_min_returns_zero(self):
        # balance=1 → invest=0.3 → qty=6e-6 < 0.001
        qty = self.runner._calculate_order_quantity(
            Decimal("1"), Decimal("50000"), "BTCUSDT", "buy"
        )
        assert qty == Decimal("0")

    def test_eth_above_min(self):
        qty = self.runner._calculate_order_quantity(
            Decimal("10000"), Decimal("2000"), "ETHUSDT", "buy"
        )
        assert qty == Decimal("3000") / Decimal("2000")

    def test_sol_above_min(self):
        qty = self.runner._calculate_order_quantity(
            Decimal("10000"), Decimal("100"), "SOLUSDT", "buy"
        )
        assert qty == Decimal("30")

    def test_other_symbol_below_min_1_returns_zero(self):
        # balance=1, price=10 → invest=0.3, qty=0.03 < 1
        qty = self.runner._calculate_order_quantity(
            Decimal("1"), Decimal("10"), "XYZUSDT", "buy"
        )
        assert qty == Decimal("0")

    def test_sell_skips_min_check(self):
        # tiny balance → qty < BTC min but sell still returns nonzero
        qty = self.runner._calculate_order_quantity(
            Decimal("1"), Decimal("50000"), "BTCUSDT", "sell"
        )
        assert qty > Decimal("0")

    def test_custom_max_invest_percent(self):
        # 10% of 1000 = 100 / 1000 = 0.1 qty < 1 (other symbol min)
        qty = self.runner._calculate_order_quantity(
            Decimal("1000"), Decimal("1000"), "XYZUSDT", "buy",
            max_invest_percent=Decimal("0.10"),
        )
        assert qty == Decimal("0")


# ==================== 单例 ====================

class TestSingleton:
    def test_same_instance_returned_twice(self):
        StrategyRunner._instance = None
        r1 = StrategyRunner()
        r2 = StrategyRunner()
        assert r1 is r2

    def teardown_method(self):
        StrategyRunner._instance = None


# ==================== 生命周期 ====================

class TestLifecycle:
    async def test_stop_cancels_all_tasks_and_clears_state(self, runner):
        t1, t2 = MagicMock(), MagicMock()
        runner._runners = {1: t1, 2: t2}
        runner._strategies = {1: MagicMock()}
        runner._last_signal_at = {1: MagicMock()}
        runner._running = True

        await runner.stop()

        t1.cancel.assert_called_once()
        t2.cancel.assert_called_once()
        assert runner._running is False
        assert runner._runners == {}
        assert runner._strategies == {}
        assert runner._last_signal_at == {}

    async def test_stop_instance_cancels_task_and_removes_from_dicts(self, runner):
        task = MagicMock()
        runner._runners = {1: task}
        runner._strategies = {1: MagicMock()}
        runner._last_signal_at = {1: MagicMock()}

        await runner.stop_instance(1)

        task.cancel.assert_called_once()
        assert 1 not in runner._runners
        assert 1 not in runner._strategies
        assert 1 not in runner._last_signal_at

    async def test_stop_nonexistent_instance_is_noop(self, runner):
        await runner.stop_instance(999)  # must not raise

    def test_get_status_not_in_runners_returns_not_running(self, runner):
        assert runner.get_status(999) == {"running": False}

    def test_get_status_running_task(self, runner):
        task = MagicMock(spec=asyncio.Task)
        task.done.return_value = False
        strategy = MagicMock()
        strategy.strategy_type = "rsi"

        runner._runners = {1: task}
        runner._strategies = {1: strategy}

        status = runner.get_status(1)
        assert status["running"] is True
        assert status["strategy_type"] == "rsi"
        assert "last_signal_at" in status

    def test_active_count(self, runner):
        runner._runners = {1: MagicMock(), 2: MagicMock()}
        assert runner.active_count == 2

    async def test_start_sets_running_and_loads_zero_instances(self, runner):
        _, session_maker = _make_session_mock(instances=[])
        await runner.start(session_maker)
        assert runner._running is True

    async def test_start_idempotent(self, runner):
        runner._running = True
        called = []

        def bad_session_maker():
            called.append(1)
            return AsyncMock()

        await runner.start(bad_session_maker)
        assert called == []


# ==================== start_instance ====================

class TestStartInstance:
    async def test_returns_false_when_already_running(self, runner):
        runner._runners = {1: MagicMock()}
        runner._session_maker = MagicMock()
        assert await runner.start_instance(1) is False

    async def test_returns_false_when_instance_not_found(self, runner):
        _, session_maker = _make_session_mock(scalar_result=None)
        runner._session_maker = session_maker
        runner._running = True

        assert await runner.start_instance(999) is False


# ==================== _handle_signal 防抖 ====================

class TestHandleSignalDebounce:
    def _config(self, auto_trade=False):
        return StrategyConfig(
            symbol="BTCUSDT", exchange="binance",
            direction="both",
            params={"auto_trade": auto_trade},
            risk_params={},
        )

    async def test_debounce_within_60s_skips_processing(self, runner):
        recent = datetime.now(timezone.utc) - timedelta(seconds=10)
        runner._last_signal_at[1] = recent

        signal = Signal(action="buy", confidence=0.8, reason="test")
        persist_called = []

        async def mock_persist(*a, **kw):
            persist_called.append(1)
            return None

        runner._persist_signal = mock_persist
        await runner._handle_signal(1, signal, self._config())
        assert persist_called == []

    async def test_first_signal_updates_last_signal_at(self, runner):
        assert 1 not in runner._last_signal_at
        signal = Signal(action="buy", confidence=0.8, reason="test")

        # _persist_signal will fail silently (no session_maker); that's fine
        await runner._handle_signal(1, signal, self._config(auto_trade=False))

        assert 1 in runner._last_signal_at

    async def test_signal_after_60s_is_processed(self, runner):
        old = datetime.now(timezone.utc) - timedelta(seconds=61)
        runner._last_signal_at[1] = old

        signal = Signal(action="sell", confidence=0.9, reason="timeout")

        persist_called = []

        async def mock_persist(*a, **kw):
            persist_called.append(1)
            return 42

        runner._persist_signal = mock_persist
        await runner._handle_signal(1, signal, self._config(auto_trade=False))
        assert persist_called == [1]


# ==================== update_stats ====================

class TestUpdateStats:
    async def test_updates_pnl_and_trades(self, runner):
        inst = MagicMock()
        inst.total_pnl = Decimal("100")
        inst.total_trades = 4
        inst.win_rate = Decimal("50.00")
        inst.params = {"initial_capital": 1000}

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = inst
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result_mock)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        runner._session_maker = lambda: session

        await runner.update_stats(1, pnl=Decimal("50"), is_win=True)

        assert inst.total_pnl == Decimal("150")
        assert inst.total_trades == 5

    async def test_instance_not_found_is_noop(self, runner):
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result_mock)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        runner._session_maker = lambda: session
        # must not raise
        await runner.update_stats(999, pnl=Decimal("10"), is_win=False)
