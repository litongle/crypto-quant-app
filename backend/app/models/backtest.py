"""
回测结果模型

存储每次回测的完整结果，包括绩效指标、权益曲线和交易记录。
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BacktestResult(Base):
    """回测结果"""

    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    # 回测配置
    template_id: Mapped[str] = mapped_column(String(50), comment="策略模板ID")
    symbol: Mapped[str] = mapped_column(String(20), comment="交易对")
    exchange: Mapped[str] = mapped_column(String(20), comment="交易所")
    start_date: Mapped[str] = mapped_column(String(20), comment="开始日期")
    end_date: Mapped[str] = mapped_column(String(20), comment="结束日期")
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(20, 8), comment="初始资金")
    params: Mapped[str | None] = mapped_column(Text, nullable=True, comment="策略参数 JSON")

    # 绩效指标
    total_return: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"), comment="总收益")
    total_return_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"), comment="总收益率%")
    annual_return: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"), comment="年化收益率%")
    sharpe_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"), comment="夏普比率")
    calmar_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"), comment="卡玛比率")
    max_drawdown: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"), comment="最大回撤%")
    win_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"), comment="胜率%")
    profit_factor: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"), comment="盈亏比")
    total_trades: Mapped[int] = mapped_column(Integer, default=0, comment="总交易次数")
    profit_trades: Mapped[int] = mapped_column(Integer, default=0, comment="盈利次数")
    loss_trades: Mapped[int] = mapped_column(Integer, default=0, comment="亏损次数")
    avg_profit: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"), comment="平均盈利")
    avg_loss: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"), comment="平均亏损")

    # 详细数据（JSON 格式）
    equity_curve: Mapped[str | None] = mapped_column(Text, nullable=True, comment="权益曲线 JSON")
    trades: Mapped[str | None] = mapped_column(Text, nullable=True, comment="交易记录 JSON")

    # 时间
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="回测开始时间")
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="回测结束时间")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<BacktestResult(id={self.id}, template={self.template_id}, symbol={self.symbol})>"
