"""每日权益快照模型 — alpha-7 P0-2

替换 AssetService.get_equity_curve 里硬编码的 100000 起点，让权益曲线
基于真实账户余额历史绘制。SyncScheduler 每 5 分钟 upsert 一次当天记录
(UNIQUE(account_id, snapshot_date))，最后一次同步即当天收盘值。
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.exchange import ExchangeAccount


class DailyEquitySnapshot(Base):
    """每日权益快照（每账户每天一条）"""

    __tablename__ = "daily_equity_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "snapshot_date", name="uq_daily_equity_snapshot_account_date"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("exchange_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    balance: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"), nullable=False)
    frozen_balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), default=Decimal("0"), nullable=False
    )
    positions_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), default=Decimal("0"), nullable=False
    )
    total_equity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), default=Decimal("0"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    account: Mapped["ExchangeAccount"] = relationship("ExchangeAccount")

    def __repr__(self) -> str:
        return (
            f"<DailyEquitySnapshot(account_id={self.account_id}, "
            f"date={self.snapshot_date}, total={self.total_equity})>"
        )
