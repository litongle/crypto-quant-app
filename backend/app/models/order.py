"""
订单模型
"""
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.exchange import ExchangeAccount


class Order(Base):
    """订单"""

    __tablename__ = "orders"
    __table_args__ = (
        # P2-6: 联合唯一约束，不同交易所订单ID可能重复
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("exchange_accounts.id"), index=True
    )
    
    # 交易所订单ID（P2-6: 去掉 unique，改为联合唯一 (exchange_order_id, account_id)）
    exchange_order_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    
    # 交易对
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    
    # 订单方向
    side: Mapped[str] = mapped_column(
        Enum("buy", "sell", name="order_side")
    )
    
    # 订单类型
    order_type: Mapped[str] = mapped_column(
        Enum("market", "limit", "stop_loss", "take_profit", name="order_type")
    )
    
    # 价格
    price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True, comment="限价单价格"
    )
    stop_price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True, comment="止损/止盈触发价格"
    )
    
    # 数量
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), comment="订单数量")
    filled_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), default=0, comment="已成交数量"
    )
    avg_fill_price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True, comment="平均成交价"
    )
    
    # 金额
    order_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), default=0, comment="订单价值(USDT)"
    )
    commission: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), default=0, comment="手续费"
    )
    pnl: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True, default=None, comment="已实现盈亏"
    )
    
    # 状态
    status: Mapped[str] = mapped_column(
        Enum(
            "pending", "submitted", "partial", "filled", 
            "cancelled", "rejected", name="order_status"
        ),
        default="pending",
    )
    
    # 来源
    strategy_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_instances.id"), nullable=True, index=True
    )
    signal_id: Mapped[int | None] = mapped_column(
        ForeignKey("signals.id", use_alter=True, name="fk_order_signal_id"), nullable=True, index=True
    )
    
    # 备注
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # 时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    filled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    account: Mapped["ExchangeAccount"] = relationship(
        "ExchangeAccount", back_populates="orders"
    )

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, symbol={self.symbol}, side={self.side}, status={self.status})>"


class Signal(Base):
    """交易信号"""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # 策略信息
    strategy_instance_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_instances.id"), index=True
    )
    
    # 交易对
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    
    # 信号动作
    action: Mapped[str] = mapped_column(
        Enum("buy", "sell", "close", name="signal_action")
    )
    
    # 信号详情
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), comment="置信度 0.0000 - 1.0000"
    )
    entry_price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True, comment="建议入场价格"
    )
    stop_loss_price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True
    )
    take_profit_price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True
    )
    
    # 信号状态
    status: Mapped[str] = mapped_column(
        Enum("pending", "confirmed", "expired", "executed", "rejected", name="signal_status"),
        default="pending",
    )
    
    # 执行信息
    executed_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", use_alter=True, name="fk_signal_order_id"), nullable=True
    )
    
    # 市场数据快照（JSON格式存储，非ForeignKey）
    market_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="市场数据快照"
    )
    
    # 原因
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # 时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Signal(id={self.id}, action={self.action}, symbol={self.symbol})>"
