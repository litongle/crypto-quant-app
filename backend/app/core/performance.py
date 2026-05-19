"""
绩效计算模块

提供策略和账户层面的绩效分析：

1. 核心指标:
   - 总收益 (Total Return)
   - 年化收益率 (Annualized Return)
   - 最大回撤 (Max Drawdown)
   - 夏普比率 (Sharpe Ratio)
   - 胜率 (Win Rate)
   - 盈亏比 (Profit/Loss Ratio)
   - 卡玛比率 (Calmar Ratio)

2. 使用方式:
   - PerformanceCalculator.calculate(orders, equity_curve) → PerformanceReport
   - 适用于回测结果 & 实盘绩效
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


@dataclass
class TradeRecord:
    """单笔交易记录（用于绩效计算）"""

    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    side: str  # long / short
    entry_time: datetime
    exit_time: datetime
    pnl: Decimal
    commission: Decimal = Decimal("0")


@dataclass
class EquityPoint:
    """权益曲线上的一个点"""

    timestamp: datetime
    equity: Decimal


@dataclass
class PerformanceReport:
    """绩效报告"""

    # 基础统计
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    # 收益指标
    total_pnl: Decimal = Decimal("0")
    total_return_pct: Decimal = Decimal("0")  # 总收益率 %
    annualized_return_pct: Decimal = Decimal("0")  # 年化收益率 %

    # 风险指标
    max_drawdown_pct: Decimal = Decimal("0")  # 最大回撤 %
    max_drawdown_duration_hours: float = 0  # 最大回撤持续时长

    # 风险调整收益
    sharpe_ratio: Decimal = Decimal("0")  # 夏普比率
    calmar_ratio: Decimal = Decimal("0")  # 卡玛比率

    # 交易质量
    win_rate: Decimal = Decimal("0")  # 胜率 %
    profit_loss_ratio: Decimal = Decimal("0")  # 盈亏比
    avg_profit: Decimal = Decimal("0")  # 平均盈利
    avg_loss: Decimal = Decimal("0")  # 平均亏损
    max_consecutive_wins: int = 0  # 最大连胜
    max_consecutive_losses: int = 0  # 最大连亏

    # 附加信息
    initial_capital: Decimal = Decimal("100000")
    final_equity: Decimal = Decimal("100000")
    trading_days: int = 0
    start_time: datetime | None = None
    end_time: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（API 响应用）"""
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl": str(self.total_pnl),
            "total_return_pct": str(round(self.total_return_pct, 4)),
            "annualized_return_pct": str(round(self.annualized_return_pct, 4)),
            "max_drawdown_pct": str(round(self.max_drawdown_pct, 4)),
            "max_drawdown_duration_hours": round(self.max_drawdown_duration_hours, 1),
            "sharpe_ratio": str(round(self.sharpe_ratio, 4)),
            "calmar_ratio": str(round(self.calmar_ratio, 4)),
            "win_rate": str(round(self.win_rate, 2)),
            "profit_loss_ratio": str(round(self.profit_loss_ratio, 4)),
            "avg_profit": str(self.avg_profit),
            "avg_loss": str(self.avg_loss),
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "initial_capital": str(self.initial_capital),
            "final_equity": str(self.final_equity),
            "trading_days": self.trading_days,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }


class PerformanceCalculator:
    """绩效计算器"""

    # 年化计算基准：365 天
    TRADING_DAYS_PER_YEAR = 365
    # 无风险利率（年化，用于夏普比率）
    RISK_FREE_RATE = Decimal("0.02")

    @classmethod
    def calculate(
        cls,
        trades: list[TradeRecord],
        equity_curve: list[EquityPoint] | None = None,
        initial_capital: Decimal = Decimal("100000"),
    ) -> PerformanceReport:
        """计算绩效报告

        Args:
            trades: 交易记录列表
            equity_curve: 权益曲线（可选，用于计算最大回撤和夏普比率）
            initial_capital: 初始资金
        """
        report = PerformanceReport(initial_capital=initial_capital)

        if not trades:
            report.final_equity = initial_capital
            return report

        # 排序交易（按退出时间）
        sorted_trades = sorted(trades, key=lambda t: t.exit_time)

        # 基础统计
        report.total_trades = len(sorted_trades)
        report.start_time = sorted_trades[0].entry_time
        report.end_time = sorted_trades[-1].exit_time

        wins = [t for t in sorted_trades if t.pnl > 0]
        losses = [t for t in sorted_trades if t.pnl <= 0]

        report.winning_trades = len(wins)
        report.losing_trades = len(losses)

        # 总盈亏
        report.total_pnl = sum((t.pnl for t in sorted_trades), Decimal("0"))

        # 如果没有权益曲线，从交易记录构建
        if not equity_curve:
            equity_curve = cls._build_equity_curve(sorted_trades, initial_capital)

        # 最终权益
        report.final_equity = equity_curve[-1].equity if equity_curve else initial_capital

        # 总收益率
        if initial_capital > 0:
            report.total_return_pct = (
                (report.final_equity - initial_capital) / initial_capital * 100
            )

        # 交易天数 — 优先用 equity_curve 范围(反映回测请求的真实时间跨度),
        # 否则回退到 trades 跨度。
        # 之前: report.start_time/end_time 取自 trades[0].entry / trades[-1].exit,
        # 是"有交易的时间跨度"。如果回测请求 30 天但策略只在中间 10 天有交易,
        # trading_days=10 → annual_return = total_return × 365/10 虚高 3 倍。
        # 用 equity_curve 范围则反映真实"持有期"。
        if equity_curve and len(equity_curve) >= 2:
            delta = equity_curve[-1].timestamp - equity_curve[0].timestamp
            report.trading_days = max(1, delta.days)
        elif report.start_time and report.end_time:
            delta = report.end_time - report.start_time
            report.trading_days = max(1, delta.days)

        # 年化收益率
        if report.trading_days > 0 and initial_capital > 0:
            total_return = float(report.final_equity / initial_capital)
            if total_return > 0:
                years = report.trading_days / cls.TRADING_DAYS_PER_YEAR
                try:
                    annualized = (total_return ** (1 / years) - 1) * 100
                    report.annualized_return_pct = Decimal(str(round(annualized, 4)))
                except (ValueError, ZeroDivisionError):
                    pass

        # 胜率
        if report.total_trades > 0:
            report.win_rate = Decimal(
                str(round(report.winning_trades / report.total_trades * 100, 2))
            )

        # 平均盈利 / 平均亏损
        if wins:
            report.avg_profit = sum((t.pnl for t in wins), Decimal("0")) / len(wins)
        if losses:
            report.avg_loss = sum((abs(t.pnl) for t in losses), Decimal("0")) / len(losses)

        # 盈亏比
        if report.avg_loss > 0:
            report.profit_loss_ratio = report.avg_profit / report.avg_loss

        # 最大连胜/连亏
        report.max_consecutive_wins, report.max_consecutive_losses = cls._calc_streaks(
            sorted_trades
        )

        # 最大回撤
        if equity_curve:
            report.max_drawdown_pct, report.max_drawdown_duration_hours = cls._calc_max_drawdown(
                equity_curve
            )

        # 夏普比率
        if equity_curve and len(equity_curve) > 1:
            report.sharpe_ratio = cls._calc_sharpe_ratio(equity_curve)

        # 卡玛比率
        if report.max_drawdown_pct > 0:
            report.calmar_ratio = report.annualized_return_pct / report.max_drawdown_pct

        return report

    @staticmethod
    def _build_equity_curve(
        trades: list[TradeRecord], initial_capital: Decimal
    ) -> list[EquityPoint]:
        """从交易记录构建权益曲线"""
        curve: list[EquityPoint] = [
            EquityPoint(
                timestamp=trades[0].entry_time if trades else datetime.now(UTC),
                equity=initial_capital,
            )
        ]
        running_equity = initial_capital

        for t in trades:
            running_equity += t.pnl - t.commission
            curve.append(
                EquityPoint(
                    timestamp=t.exit_time,
                    equity=running_equity,
                )
            )

        return curve

    @staticmethod
    def _calc_streaks(trades: list[TradeRecord]) -> tuple[int, int]:
        """计算最大连胜和最大连亏"""
        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for t in trades:
            if t.pnl > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)

        return max_wins, max_losses

    @staticmethod
    def _calc_max_drawdown(equity_curve: list[EquityPoint]) -> tuple[Decimal, float]:
        """计算最大回撤 (%) 和最长 drawdown 持续时间 (小时)。

        max_dd_duration 定义: 整个曲线上, 从某峰值到下一次 >= 该峰值 (recovery)
        的最长间隔。回测结束时仍未 recovery 的 drawdown 也计入 (从 dd 开始到末
        点距离)。

        之前算法只在 final peak_time 之后找首次 recovery 就 break,既不是"最长
        drawdown"也不是"最长 underwater 期"——是错的。重写为标准 underwater
        duration 算法。

        Returns:
            (max_drawdown_pct, max_drawdown_duration_hours)
        """
        if len(equity_curve) < 2:
            return Decimal("0"), 0.0

        peak = equity_curve[0].equity
        peak_time = equity_curve[0].timestamp
        max_dd = Decimal("0")
        max_dd_duration_hours = 0.0
        in_drawdown = False
        dd_start_time: datetime | None = None

        for point in equity_curve:
            if point.equity >= peak:
                if in_drawdown and dd_start_time is not None:
                    # 从 dd 开始到恢复 peak 的时长
                    duration = (point.timestamp - dd_start_time).total_seconds() / 3600
                    if duration > max_dd_duration_hours:
                        max_dd_duration_hours = duration
                    in_drawdown = False
                    dd_start_time = None
                peak = point.equity
                peak_time = point.timestamp
            else:
                if peak > 0:
                    dd = (peak - point.equity) / peak * 100
                    if dd > max_dd:
                        max_dd = dd
                if not in_drawdown:
                    in_drawdown = True
                    dd_start_time = peak_time  # drawdown 从上次 peak 开始

        # 回测结束仍在 drawdown — 用末点时间记录(underwater 未恢复)
        if in_drawdown and dd_start_time is not None and equity_curve:
            duration = (equity_curve[-1].timestamp - dd_start_time).total_seconds() / 3600
            if duration > max_dd_duration_hours:
                max_dd_duration_hours = duration

        return max_dd, max_dd_duration_hours

    @classmethod
    def _calc_sharpe_ratio(cls, equity_curve: list[EquityPoint]) -> Decimal:
        """计算夏普比率(基于 equity_curve 实际采样周期年化)。

        Sharpe = (R_p - R_f) / σ_p
        - R_p = 年化收益率
        - R_f = 无风险利率
        - σ_p = 收益率标准差(年化)

        之前 bug: equity_curve 按 K 线周期采样(1h/5m/15m...), 但年化倍数
        硬编码 TRADING_DAYS_PER_YEAR(365), 仅在"日"级 K 线下正确。1h K 线
        每天 24 个点, 应该用 365*24 年化, 否则 sharpe 低估 sqrt(24)≈4.9 倍;
        5m 低估 sqrt(288)≈17 倍。修: 从 equity_curve.timestamp 推真实周期。
        """
        if len(equity_curve) < 2:
            return Decimal("0")

        # 推导每年采样点数:从相邻两点 timestamp 间隔反推
        try:
            dt_seconds = (equity_curve[1].timestamp - equity_curve[0].timestamp).total_seconds()
        except (AttributeError, TypeError):
            dt_seconds = 0
        if dt_seconds <= 0:
            # fallback 到"日"假设(向后兼容,但有 log 提示)
            points_per_year = cls.TRADING_DAYS_PER_YEAR
        else:
            points_per_year = cls.TRADING_DAYS_PER_YEAR * 86400 / dt_seconds

        # 周期收益率序列(不再叫"日"收益率)
        period_returns: list[float] = []
        for i in range(1, len(equity_curve)):
            prev = float(equity_curve[i - 1].equity)
            curr = float(equity_curve[i].equity)
            if prev > 0:
                period_returns.append((curr - prev) / prev)

        if len(period_returns) < 2:
            return Decimal("0")

        avg_return = sum(period_returns) / len(period_returns)
        variance = sum((r - avg_return) ** 2 for r in period_returns) / (len(period_returns) - 1)
        std_dev = math.sqrt(variance) if variance > 0 else 0
        if std_dev == 0:
            return Decimal("0")

        annualized_return = avg_return * points_per_year
        annualized_std = std_dev * math.sqrt(points_per_year)
        annualized_rf = float(cls.RISK_FREE_RATE)  # risk_free_rate 本身就是年化值

        sharpe = (annualized_return - annualized_rf) / annualized_std
        return Decimal(str(round(sharpe, 4)))

    @classmethod
    def from_order_models(
        cls, orders: list[Any], initial_capital: Decimal = Decimal("100000")
    ) -> PerformanceReport:
        """从 ORM Order 对象列表计算绩效

        便捷方法，直接接受 SQLAlchemy Order 模型列表。
        """
        trades: list[TradeRecord] = []

        for o in orders:
            if not hasattr(o, "pnl") or o.pnl is None:
                continue
            if not hasattr(o, "filled_quantity") or not o.filled_quantity:
                continue

            entry_price = (
                getattr(o, "avg_fill_price", None) or getattr(o, "price", None) or Decimal("0")
            )
            exit_price = entry_price  # 简化：单笔订单视为完整交易
            quantity = getattr(o, "filled_quantity", Decimal("0"))
            side = getattr(o, "side", "long")
            entry_time = getattr(o, "created_at", None) or datetime.now(UTC)
            exit_time = (
                getattr(o, "filled_at", None) or getattr(o, "updated_at", None) or entry_time
            )
            pnl = o.pnl or Decimal("0")
            commission = getattr(o, "commission", Decimal("0"))

            trades.append(
                TradeRecord(
                    entry_price=entry_price,
                    exit_price=exit_price,
                    quantity=quantity,
                    side=side,
                    entry_time=entry_time,
                    exit_time=exit_time,
                    pnl=pnl,
                    commission=commission,
                )
            )

        return cls.calculate(trades, initial_capital=initial_capital)
