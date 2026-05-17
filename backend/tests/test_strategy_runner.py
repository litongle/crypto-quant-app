"""
策略运行器单元测试 — select_position_to_close、数量计算、生命周期管理
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exchanges.base import Kline
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
        qty = self.runner._calculate_order_quantity(Decimal("1"), Decimal("10"), "XYZUSDT", "buy")
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
            Decimal("1000"),
            Decimal("1000"),
            "XYZUSDT",
            "buy",
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
        assert runner.get_status(999) == {
            "running": False,
            "runtime_active": False,
            "runtime_healthy": True,
            "last_error": None,
            "last_error_at": None,
        }

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
        await runner.stop()

    async def test_start_idempotent(self, runner):
        runner._running = True
        called = []

        def bad_session_maker():
            called.append(1)
            return AsyncMock()

        await runner.start(bad_session_maker)
        assert called == []


class TestFetchKlines:
    async def test_normalizes_datetime_timestamp_to_milliseconds(self, runner, monkeypatch):
        fake_klines = [
            Kline(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("105"),
                volume=Decimal("1.5"),
                close_time=datetime(2024, 1, 1, 1, tzinfo=UTC),
            )
        ]

        adapter = MagicMock()
        adapter.get_klines = AsyncMock(return_value=fake_klines)

        monkeypatch.setattr(
            "app.core.exchange_adapter.get_exchange_adapter",
            lambda **kwargs: adapter,
        )

        result = await runner._fetch_klines("binance", "BTCUSDT", 1, "1h")

        assert result[0]["timestamp"] == 1_704_067_200_000
        assert result[0]["close"] == 105.0


# ==================== start_instance ====================


class TestStartInstance:
    async def test_returns_false_when_already_running(self, runner):
        runner._runners = {1: MagicMock()}
        runner._session_maker = MagicMock()
        runner._runners[1].done.return_value = False
        assert await runner.start_instance(1) is False

    async def test_returns_false_when_instance_not_found(self, runner):
        _, session_maker = _make_session_mock(scalar_result=None)
        runner._session_maker = session_maker
        runner._running = True

        assert await runner.start_instance(999) is False

    async def test_cleans_finished_task_before_restart(self, runner):
        inst = MagicMock()
        done_task = MagicMock()
        done_task.done.return_value = True
        runner._runners = {1: done_task}
        runner._strategies = {1: MagicMock()}
        runner._session_maker = _make_session_mock(scalar_result=inst)[1]
        runner._running = True

        started = []

        async def fake_start_instance(inner_inst):
            started.append(inner_inst)

        runner._start_instance = fake_start_instance

        assert await runner.start_instance(1) is True
        assert started == [inst]
        assert 1 not in runner._strategies

    async def test_restart_instance_awaits_stop(self, runner):
        calls = []

        async def fake_stop(instance_id):
            calls.append(("stop", instance_id))

        async def fake_start(instance_id):
            calls.append(("start", instance_id))
            return True

        runner.stop_instance = fake_stop
        runner.start_instance = fake_start

        assert await StrategyRunner.restart_instance(runner, 7) is True
        assert calls == [("stop", 7), ("start", 7)]


# ==================== _handle_signal 防抖 ====================


class TestHandleSignalDebounce:
    def _config(self, auto_trade=False):
        return StrategyConfig(
            symbol="BTCUSDT",
            exchange="binance",
            direction="both",
            params={"auto_trade": auto_trade},
            risk_params={},
        )

    async def test_debounce_within_60s_skips_processing(self, runner):
        recent = datetime.now(UTC) - timedelta(seconds=10)
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
        old = datetime.now(UTC) - timedelta(seconds=61)
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


# ==================== _update_signal_status — 防双重 reason 追加 ====================


class TestUpdateSignalStatusNoDoubleReject:
    """signal.reason 双重追加曾导致 summary 200 截断（[下单失败][502:OKX...]）。

    回归：内层 _auto_open_position 已标 rejected → 外层 except 看到异常再调一次
    应当被跳过，不能继续追加更长的 exc 字符串到 reason。
    """

    @pytest.mark.asyncio
    async def test_second_reject_call_skipped(self, runner):
        # 第一次：signal.status=pending → 调 rejected, reason="下单失败" → 写入
        # 第二次：signal.status=rejected → 调 rejected, reason="502:..." → 应跳过
        fake_signal = MagicMock()
        fake_signal.status = "pending"
        fake_signal.reason = "RSI_SHORT_OPEN rsi=72"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_signal
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result_mock)
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        runner._session_maker = lambda: session

        await runner._update_signal_status(1, "rejected", reason="下单失败")
        assert fake_signal.status == "rejected"
        assert fake_signal.reason == "RSI_SHORT_OPEN rsi=72 [下单失败]"
        first_commits = session.commit.await_count

        # 第二次调用：已 rejected,应该 early return（不动 reason、不再 commit）
        await runner._update_signal_status(1, "rejected", reason="502: 交易所下单失败: OKX...")
        assert fake_signal.reason == "RSI_SHORT_OPEN rsi=72 [下单失败]"  # 未追加
        assert session.commit.await_count == first_commits  # 没再 commit

    @pytest.mark.asyncio
    async def test_executed_after_pending_still_works(self, runner):
        """正常路径不受影响：pending → executed 仍能写入 order_id。"""
        fake_signal = MagicMock()
        fake_signal.status = "pending"
        fake_signal.reason = "RSI"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_signal
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result_mock)
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        runner._session_maker = lambda: session

        await runner._update_signal_status(1, "executed", order_id=42)
        assert fake_signal.status == "executed"
        assert fake_signal.executed_order_id == 42
        session.commit.assert_awaited_once()
