"""
策略模型
"""
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.exchange import ExchangeAccount


class StrategyTemplate(Base):
    """策略模板"""

    __tablename__ = "strategy_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # 字符串ID: ma_cross, grid, rsi, bollinger
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    strategy_type: Mapped[str] = mapped_column(
        Enum("ma", "rsi", "bollinger", "grid", "martingale", name="strategy_type")
    )
    params_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_level: Mapped[str] = mapped_column(
        Enum("low", "medium", "high", name="strategy_risk_level"),
        default="medium",
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<StrategyTemplate(id={self.id}, code={self.code}, name={self.name})>"


class StrategyInstance(Base):
    """策略实例（用户配置的策略）"""

    __tablename__ = "strategy_instances"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("strategy_templates.id"))
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("exchange_accounts.id"), nullable=True, index=True,
        comment="绑定的交易所账户，自动下单时使用",
    )
    name: Mapped[str] = mapped_column(String(100))
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    exchange: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(
        Enum("long", "short", "both", name="strategy_direction"),
        default="both",
    )
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_params: Mapped[dict] = mapped_column(JSON, default=dict)
    # 状态: draft(草稿), running(运行中), paused(暂停), stopped(已停止)
    status: Mapped[str] = mapped_column(
        Enum("draft", "running", "paused", "stopped", name="instance_status"),
        default="draft",
    )
    # 统计字段
    total_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    total_pnl_percent: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))
    win_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    # 时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="strategies")
    template: Mapped["StrategyTemplate"] = relationship()
    account: Mapped["ExchangeAccount | None"] = relationship()

    def __repr__(self) -> str:
        return f"<StrategyInstance(id={self.id}, name={self.name}, status={self.status})>"
