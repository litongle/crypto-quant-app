"""
操作审计日志模型 - P1-6

记录所有写操作：下单、修改参数、止损止盈设置等。
支持按用户、操作类型、时间范围查询。
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    """操作审计日志"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, comment="操作用户")

    # 操作分类
    action: Mapped[str] = mapped_column(
        String(50),
        index=True,
        comment="操作类型: order_create/order_submit/order_cancel/param_update/stop_loss_set/take_profit_set/account_update/strategy_start/strategy_stop",
    )
    resource: Mapped[str] = mapped_column(
        String(50), nullable=True, comment="资源类型: order/strategy/account/position"
    )
    resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="资源ID")

    # 操作详情
    detail: Mapped[str | None] = mapped_column(Text, nullable=True, comment="操作描述")
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="变更前数据快照")
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="变更后数据快照")

    # 上下文
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True, comment="客户端IP")
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True, comment="User-Agent")

    # 结果
    status: Mapped[str] = mapped_column(
        String(20), default="success", comment="操作结果: success/failure/error"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action}, user_id={self.user_id})>"
