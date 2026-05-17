"""add audit_events table

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-17

承接没有业务表落处的事件：risk_alert（告警 — 之前只发 Telegram/邮件不落库）、
user_action（启停/改参数等审计 — 之前完全没有记录）、system（应用启停 / 对账触发）。

signal / order / auto_pause 仍由 events.py 从业务表派生，不写入这张表。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "type",
            sa.String(32),
            nullable=False,
            comment="risk_alert / user_action / system / 未来扩展",
        ),
        sa.Column(
            "severity",
            sa.String(16),
            nullable=False,
            server_default="info",
            comment="info / warning / error / critical",
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "instance_id",
            sa.Integer(),
            sa.ForeignKey("strategy_instances.id"),
            nullable=True,
        ),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("exchange_accounts.id"),
            nullable=True,
        ),
        sa.Column("summary", sa.String(200), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("ix_audit_events_type", "audit_events", ["type"])
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_instance_id", "audit_events", ["instance_id"])
    op.create_index("ix_audit_events_account_id", "audit_events", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_account_id", "audit_events")
    op.drop_index("ix_audit_events_instance_id", "audit_events")
    op.drop_index("ix_audit_events_user_id", "audit_events")
    op.drop_index("ix_audit_events_type", "audit_events")
    op.drop_index("ix_audit_events_created_at", "audit_events")
    op.drop_table("audit_events")
