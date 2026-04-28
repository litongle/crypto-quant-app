"""
绩效计算测试 — 覆盖 PerformanceCalculator 核心指标
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.performance import (
    EquityPoint,
    PerformanceCalculator,
    PerformanceReport,
    TradeRecord,
)


def _ts(days: int = 0, hours: int = 0) -> datetime:
    """Construct a deterministic UTC timestamp offset from a fixed base."""
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return base + timedelta(days=days, hours=hours)


def _trade(
    pnl: str,
    *,
    entry_day: int = 0,
    exit_day: int = 1,
    side: str = "long",
    entry_price: str = "100",
    exit_price: str = "110",
    quantity: str = "1",
    commission: str = "0",
) -> TradeRecord:
    return TradeRecord(
        entry_price=Decimal(entry_price),
        exit_price=Decimal(exit_price),
        quantity=Decimal(quantity),
        side=side,
        entry_time=_ts(days=entry_day),
        exit_time=_ts(days=exit_day),
        pnl=Decimal(pnl),
        commission=Decimal(commission),
    )


class TestEmptyTrades:
    """边界条件：无交易"""

    def test_empty_trades_returns_default_report(self):
        report = PerformanceCalculator.calculate([])
        assert isinstance(report, PerformanceReport)
        assert report.total_trades == 0
        assert report.winning_trades == 0
        assert report.losing_trades == 0
        assert report.total_pnl == Decimal("0")
        assert report.final_equity == Decimal("100000")

    def test_empty_trades_custom_capital(self):
        report = PerformanceCalculator.calculate(
            [], initial_capital=Decimal("50000")
        )
        assert report.initial_capital == Decimal("50000")
        assert report.final_equity == Decimal("50000")


class TestBasicStats:
    """基础统计：胜负数、总盈亏"""

    def test_single_winning_trade(self):
        report = PerformanceCalculator.calculate([_trade("100")])
        assert report.total_trades == 1
        assert report.winning_trades == 1
        assert report.losing_trades == 0
        assert report.total_pnl == Decimal("100")

    def test_single_losing_trade(self):
        report = PerformanceCalculator.calculate([_trade("-50")])
        assert report.total_trades == 1
        assert report.winning_trades == 0
        assert report.losing_trades == 1
        assert report.total_pnl == Decimal("-50")

    def test_zero_pnl_treated_as_losing(self):
        # 实现里 pnl <= 0 算作 loss
        report = PerformanceCalculator.calculate([_trade("0")])
        assert report.winning_trades == 0
        assert report.losing_trades == 1

    def test_mixed_trades(self):
        trades = [
            _trade("100", entry_day=0, exit_day=1),
            _trade("-30", entry_day=1, exit_day=2),
            _trade("50", entry_day=2, exit_day=3),
        ]
        report = PerformanceCalculator.calculate(trades)
        assert report.total_trades == 3
        assert report.winning_trades == 2
        assert report.losing_trades == 1
        assert report.total_pnl == Decimal("120")


class TestWinRate:
    def test_all_wins(self):
        trades = [_trade("10", entry_day=i, exit_day=i + 1) for i in range(3)]
        report = PerformanceCalculator.calculate(trades)
        assert report.win_rate == Decimal("100.00")

    def test_all_losses(self):
        trades = [_trade("-10", entry_day=i, exit_day=i + 1) for i in range(3)]
        report = PerformanceCalculator.calculate(trades)
        assert report.win_rate == Decimal("0.00")

    def test_mixed_win_rate(self):
        trades = [
            _trade("10", entry_day=0, exit_day=1),
            _trade("-10", entry_day=1, exit_day=2),
            _trade("10", entry_day=2, exit_day=3),
            _trade("-10", entry_day=3, exit_day=4),
        ]
        report = PerformanceCalculator.calculate(trades)
        assert report.win_rate == Decimal("50.00")


class TestProfitLossRatio:
    def test_avg_profit_and_loss(self):
        trades = [
            _trade("100", entry_day=0, exit_day=1),
            _trade("200", entry_day=1, exit_day=2),
            _trade("-50", entry_day=2, exit_day=3),
        ]
        report = PerformanceCalculator.calculate(trades)
        assert report.avg_profit == Decimal("150")
        assert report.avg_loss == Decimal("50")
        assert report.profit_loss_ratio == Decimal("3")

    def test_no_loss_means_zero_ratio(self):
        report = PerformanceCalculator.calculate([_trade("100")])
        # 没有亏损交易时 profit_loss_ratio 保持默认 0（不能除以 0）
        assert report.profit_loss_ratio == Decimal("0")


class TestStreaks:
    def test_max_consecutive_wins(self):
        trades = [_trade("10", entry_day=i, exit_day=i + 1) for i in range(5)]
        report = PerformanceCalculator.calculate(trades)
        assert report.max_consecutive_wins == 5
        assert report.max_consecutive_losses == 0

    def test_max_consecutive_losses(self):
        trades = [_trade("-10", entry_day=i, exit_day=i + 1) for i in range(4)]
        report = PerformanceCalculator.calculate(trades)
        assert report.max_consecutive_wins == 0
        assert report.max_consecutive_losses == 4

    def test_alternating_streaks(self):
        # W L W W L L L W
        pnls = ["10", "-5", "20", "30", "-1", "-2", "-3", "40"]
        trades = [
            _trade(p, entry_day=i, exit_day=i + 1) for i, p in enumerate(pnls)
        ]
        report = PerformanceCalculator.calculate(trades)
        assert report.max_consecutive_wins == 2
        assert report.max_consecutive_losses == 3


class TestTotalReturn:
    def test_total_return_pct(self):
        # 单笔盈利 1000，初始 10000 → 10%
        trade = _trade("1000")
        report = PerformanceCalculator.calculate(
            [trade], initial_capital=Decimal("10000")
        )
        assert report.final_equity == Decimal("11000")
        assert report.total_return_pct == Decimal("10")

    def test_negative_total_return(self):
        trade = _trade("-2000")
        report = PerformanceCalculator.calculate(
            [trade], initial_capital=Decimal("10000")
        )
        assert report.final_equity == Decimal("8000")
        assert report.total_return_pct == Decimal("-20")


class TestMaxDrawdown:
    """最大回撤计算"""

    def test_no_drawdown_when_monotonic_increase(self):
        equity = [
            EquityPoint(_ts(days=i), Decimal(str(100 + i * 10)))
            for i in range(5)
        ]
        max_dd, _ = PerformanceCalculator._calc_max_drawdown(equity)
        assert max_dd == Decimal("0")

    def test_simple_drawdown(self):
        # 100 → 200 (peak) → 150 → 200 → ...
        # drawdown = (200-150)/200 * 100 = 25%
        equity = [
            EquityPoint(_ts(days=0), Decimal("100")),
            EquityPoint(_ts(days=1), Decimal("200")),
            EquityPoint(_ts(days=2), Decimal("150")),
            EquityPoint(_ts(days=3), Decimal("220")),
        ]
        max_dd, _ = PerformanceCalculator._calc_max_drawdown(equity)
        assert max_dd == Decimal("25")

    def test_drawdown_from_initial_peak(self):
        equity = [
            EquityPoint(_ts(days=0), Decimal("1000")),
            EquityPoint(_ts(days=1), Decimal("500")),
        ]
        max_dd, _ = PerformanceCalculator._calc_max_drawdown(equity)
        assert max_dd == Decimal("50")

    def test_drawdown_short_curve(self):
        # 单点曲线返回 0
        equity = [EquityPoint(_ts(days=0), Decimal("100"))]
        max_dd, duration = PerformanceCalculator._calc_max_drawdown(equity)
        assert max_dd == Decimal("0")
        assert duration == 0.0


class TestSharpeRatio:
    def test_sharpe_zero_when_constant_equity(self):
        equity = [
            EquityPoint(_ts(days=i), Decimal("100")) for i in range(10)
        ]
        sharpe = PerformanceCalculator._calc_sharpe_ratio(equity)
        # 收益率全为 0 → std=0 → sharpe=0
        assert sharpe == Decimal("0")

    def test_sharpe_positive_when_steady_growth(self):
        # 持续增长应当产生正夏普
        equity = [
            EquityPoint(_ts(days=i), Decimal(str(100 * (1.001 ** i))))
            for i in range(30)
        ]
        sharpe = PerformanceCalculator._calc_sharpe_ratio(equity)
        assert sharpe > Decimal("0")

    def test_sharpe_short_curve(self):
        equity = [EquityPoint(_ts(days=0), Decimal("100"))]
        sharpe = PerformanceCalculator._calc_sharpe_ratio(equity)
        assert sharpe == Decimal("0")


class TestEquityCurveBuild:
    def test_build_from_trades(self):
        trades = [_trade("100", entry_day=0, exit_day=1, commission="5")]
        curve = PerformanceCalculator._build_equity_curve(
            trades, Decimal("10000")
        )
        assert len(curve) == 2
        assert curve[0].equity == Decimal("10000")
        # initial + pnl - commission = 10000 + 100 - 5 = 10095
        assert curve[1].equity == Decimal("10095")


class TestCalmarRatio:
    def test_calmar_requires_drawdown(self):
        # 无回撤时 calmar 为 0
        trade = _trade("100", entry_day=0, exit_day=1)
        report = PerformanceCalculator.calculate(
            [trade], initial_capital=Decimal("10000")
        )
        # 单笔盈利的曲线只往上走，无回撤
        assert report.calmar_ratio == Decimal("0")


class TestSerialization:
    def test_to_dict_keys(self):
        report = PerformanceCalculator.calculate(
            [_trade("100")], initial_capital=Decimal("10000")
        )
        d = report.to_dict()
        # 关键字段都在
        assert "total_trades" in d
        assert "win_rate" in d
        assert "sharpe_ratio" in d
        assert "max_drawdown_pct" in d
        assert "total_return_pct" in d
        # 数字字段已转字符串
        assert isinstance(d["total_pnl"], str)
        assert isinstance(d["total_trades"], int)

    def test_to_dict_handles_none_timestamps(self):
        report = PerformanceReport()
        d = report.to_dict()
        assert d["start_time"] is None
        assert d["end_time"] is None


class TestFromOrderModels:
    """from_order_models 适配 ORM 对象"""

    def test_skips_orders_without_pnl(self):
        class FakeOrder:
            pnl = None
            filled_quantity = Decimal("1")

        report = PerformanceCalculator.from_order_models([FakeOrder()])
        assert report.total_trades == 0

    def test_skips_orders_without_fill(self):
        class FakeOrder:
            pnl = Decimal("10")
            filled_quantity = Decimal("0")

        report = PerformanceCalculator.from_order_models([FakeOrder()])
        assert report.total_trades == 0

    def test_includes_valid_orders(self):
        class FakeOrder:
            pnl = Decimal("100")
            filled_quantity = Decimal("1")
            avg_fill_price = Decimal("50000")
            price = Decimal("50000")
            side = "long"
            created_at = _ts(days=0)
            filled_at = _ts(days=1)
            updated_at = _ts(days=1)
            commission = Decimal("0")

        report = PerformanceCalculator.from_order_models([FakeOrder()])
        assert report.total_trades == 1
        assert report.total_pnl == Decimal("100")
