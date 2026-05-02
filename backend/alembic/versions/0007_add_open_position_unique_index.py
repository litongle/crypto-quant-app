"""
数据库迁移: 为 positions 添加仅限 open 状态的联合唯一索引

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_open_position_account_symbol_side",
        "positions",
        ["account_id", "symbol", "side"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
        sqlite_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index("uq_open_position_account_symbol_side", table_name="positions")
