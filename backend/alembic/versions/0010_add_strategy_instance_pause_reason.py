"""add strategy_instances.last_pause_reason

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-09 00:00:00.000000

auto-pause v1: 记录策略自停原因，区分用户操作（NULL）与系统判定（auto:*）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "strategy_instances",
        sa.Column(
            "last_pause_reason",
            sa.String(length=64),
            nullable=True,
            comment="自停原因 — auto:consecutive_errors / auto:order_failures / auto:heartbeat_timeout；NULL=用户手动操作",
        ),
    )


def downgrade() -> None:
    op.drop_column("strategy_instances", "last_pause_reason")
