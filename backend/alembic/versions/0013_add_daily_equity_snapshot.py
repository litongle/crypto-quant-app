"""add daily_equity_snapshot table

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-15

每日权益快照，每个 ExchangeAccount 一条/天，由 SyncScheduler 每 5
分钟 upsert 当日记录（最后一次 sync 即当日收盘值）。AssetService
.get_equity_curve 改读这张表替换硬编码 100000 起点。

冷启动 backfill：升级时为每个 active 账户写入今天的初始快照（仅
balance + frozen_balance，positions_value 留 0；后续 scheduler 会
覆盖含持仓估值的完整值）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_equity_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("exchange_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column(
            "balance",
            sa.Numeric(20, 8),
            nullable=False,
            server_default="0",
            comment="可用余额(USDT)",
        ),
        sa.Column(
            "frozen_balance",
            sa.Numeric(20, 8),
            nullable=False,
            server_default="0",
            comment="冻结余额(USDT)",
        ),
        sa.Column(
            "positions_value",
            sa.Numeric(20, 8),
            nullable=False,
            server_default="0",
            comment="持仓估值 sum(qty * mark_price + unrealized_pnl)",
        ),
        sa.Column(
            "total_equity",
            sa.Numeric(20, 8),
            nullable=False,
            server_default="0",
            comment="balance + frozen + positions_value",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "account_id", "snapshot_date", name="uq_daily_equity_snapshot_account_date"
        ),
    )
    op.create_index(
        "ix_daily_equity_snapshot_date",
        "daily_equity_snapshot",
        ["snapshot_date"],
    )
    op.create_index(
        "ix_daily_equity_snapshot_account_id",
        "daily_equity_snapshot",
        ["account_id"],
    )

    # 冷启动 backfill：为每个 active 账户写一条今天的快照，positions_value=0
    # （scheduler 启动后 5 分钟内会覆盖含持仓估值的完整值）。
    op.execute(
        """
        INSERT INTO daily_equity_snapshot
            (account_id, snapshot_date, balance, frozen_balance, positions_value, total_equity)
        SELECT
            id,
            CURRENT_DATE,
            COALESCE(balance, 0),
            COALESCE(frozen_balance, 0),
            0,
            COALESCE(balance, 0) + COALESCE(frozen_balance, 0)
        FROM exchange_accounts
        WHERE is_active = true AND status = 'active'
        ON CONFLICT (account_id, snapshot_date) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_daily_equity_snapshot_account_id", "daily_equity_snapshot")
    op.drop_index("ix_daily_equity_snapshot_date", "daily_equity_snapshot")
    op.drop_table("daily_equity_snapshot")
