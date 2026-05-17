"""审计事件模型 — 风控告警 / 用户操作 / 系统事件的持久化日志。

与 signal / order / strategy_instance.last_pause_reason 不同的是：
- signal / order 事件是从业务表派生（events.py 序列化它们）
- auto_pause 历史会被 last_pause_reason 字段覆盖，只有最新一次
- 而这张表承接「没有业务表落处」的事件：risk_alert（告警）、user_action
  （启停/改参数等审计）、system（应用启停 / watchdog 触发）

数据写入只增不改 — 这是审计表，不允许 update。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_created_at", "created_at"),
        Index("ix_audit_events_type", "type"),
        Index("ix_audit_events_user_id", "user_id"),
        Index("ix_audit_events_instance_id", "instance_id"),
        Index("ix_audit_events_account_id", "account_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 用 String 而非 Enum — 后续新增事件类型无需迁移
    type: Mapped[str] = mapped_column(
        String(32),
        comment="risk_alert / user_action / system / 未来扩展",
    )
    severity: Mapped[str] = mapped_column(
        String(16),
        default="info",
        server_default="info",
        comment="info / warning / error / critical",
    )

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_instances.id"), nullable=True
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("exchange_accounts.id"), nullable=True
    )

    summary: Mapped[str] = mapped_column(String(200))
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<AuditEvent(id={self.id}, type={self.type}, "
            f"severity={self.severity}, summary={self.summary[:30]!r})>"
        )
