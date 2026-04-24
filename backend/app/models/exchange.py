"""
交易所账户模型
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
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class ExchangeAccount(Base):
    """交易所账户"""

    __tablename__ = "exchange_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    exchange: Mapped[str] = mapped_column(
        Enum("binance", "okx", "huobi", name="exchange_name")
    )
    account_name: Mapped[str] = mapped_column(String(100), comment="账户别名")
    
    # API Key 加密存储
    encrypted_api_key: Mapped[str] = mapped_column(Text, comment="AES-256加密的API Key")
    encrypted_secret_key: Mapped[str] = mapped_column(Text, comment="AES-256加密的Secret Key")
    encrypted_passphrase: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="OKX需要AES-256加密的passphrase"
    )

    def set_api_key(self, plaintext: str) -> None:
        """加密并设置 API Key"""
        from app.core.security import encrypt_api_key
        self.encrypted_api_key = encrypt_api_key(plaintext)

    def get_api_key(self) -> str:
        """解密并获取 API Key"""
        from app.core.security import decrypt_api_key
        return decrypt_api_key(self.encrypted_api_key)

    def set_secret_key(self, plaintext: str) -> None:
        """加密并设置 Secret Key"""
        from app.core.security import encrypt_api_key
        self.encrypted_secret_key = encrypt_api_key(plaintext)

    def get_secret_key(self) -> str:
        """解密并获取 Secret Key"""
        from app.core.security import decrypt_api_key
        return decrypt_api_key(self.encrypted_secret_key)

    def set_passphrase(self, plaintext: str) -> None:
        """加密并设置 Passphrase"""
        from app.core.security import encrypt_api_key
        self.encrypted_passphrase = encrypt_api_key(plaintext)

    def get_passphrase(self) -> str:
        """解密并获取 Passphrase"""
        from app.core.security import decrypt_api_key
        return decrypt_api_key(self.encrypted_passphrase or "")
    
    # 权限控制
    permissions: Mapped[str] = mapped_column(
        String(50), default="read,trade", comment="API权限: read,trade,withdraw"
    )

    # 环境标识（明确区分模拟盘/测试网 vs 真实盘）
    is_demo: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="OKX模拟盘标记(x-simulated-trading)"
    )
    is_testnet: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="Binance测试网标记"
    )
    
    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(
        Enum("active", "error", "disabled", name="account_status"),
        default="active",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 账户余额（从交易所同步）
    balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), default=Decimal("0"), comment="可用余额(USDT)"
    )
    frozen_balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), default=Decimal("0"), comment="冻结余额(USDT)"
    )
    
    # 同步状态
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="accounts")
    positions: Mapped[list["Position"]] = relationship(
        "Position", back_populates="account", lazy="selectin"
    )
    orders: Mapped[list["Order"]] = relationship(
        "Order", back_populates="account", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<ExchangeAccount(id={self.id}, exchange={self.exchange})>"


class Position(Base):
    """持仓"""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("exchange_accounts.id"), index=True)
    
    # 交易对信息
    symbol: Mapped[str] = mapped_column(String(20), index=True, comment="交易对 BTC/USDT")
    side: Mapped[str] = mapped_column(
        Enum("long", "short", name="position_side")
    )
    
    # 持仓信息
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), comment="持仓数量")
    entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), comment="开仓价格")
    current_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), comment="当前价格")
    
    # 杠杆
    leverage: Mapped[int] = mapped_column(Integer, default=1)
    
    # 盈亏
    unrealized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), default=0, comment="未实现盈亏"
    )
    unrealized_pnl_percent: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=0, comment="未实现盈亏百分比"
    )
    
    # 止盈止损
    stop_loss_price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True
    )
    take_profit_price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True
    )
    
    # 状态
    status: Mapped[str] = mapped_column(
        Enum("open", "closed", "liquidated", name="position_status"),
        default="open",
    )
    
    # 来源
    strategy_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_instances.id"), nullable=True, index=True
    )
    
    # 时间
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    account: Mapped["ExchangeAccount"] = relationship(
        "ExchangeAccount", back_populates="positions"
    )

    def __repr__(self) -> str:
        return f"<Position(id={self.id}, symbol={self.symbol}, side={self.side})>"
