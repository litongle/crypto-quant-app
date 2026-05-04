"""
数据库迁移: 交易账户增加本地模拟盘与合约设置字段

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "exchange_accounts",
        sa.Column(
            "is_paper",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="本地模拟盘标记（由本系统撮合，不调用交易所）",
        ),
    )
    op.add_column(
        "exchange_accounts",
        sa.Column(
            "balances",
            sa.JSON(),
            nullable=True,
            comment="账户资产明细快照（本地模拟盘会维护各币种余额）",
        ),
    )
    op.add_column(
        "exchange_accounts",
        sa.Column(
            "contract_settings",
            sa.JSON(),
            nullable=True,
            comment="合约交易设置（按交易对保存杠杆与保证金模式）",
        ),
    )
    op.alter_column("exchange_accounts", "is_paper", server_default=None)


def downgrade() -> None:
    op.drop_column("exchange_accounts", "contract_settings")
    op.drop_column("exchange_accounts", "balances")
    op.drop_column("exchange_accounts", "is_paper")
