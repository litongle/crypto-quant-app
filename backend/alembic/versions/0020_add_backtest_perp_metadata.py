"""add backtest perp metadata columns

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-19

让历史回测能完整复现 perp 元数据：market / data_source / leverage /
funding_fee_total / max_drawdown_duration_hours。

之前这些字段算出来塞进 result dict 返给前端实时显示，但持久化层丢了，
点开历史就看不到 funding 累计、杠杆等关键信息。

全部 nullable，老数据查询保持 None。SQLite + PG 通用类型。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "backtest_results",
        sa.Column("market", sa.String(10), nullable=True, comment="市场类型 spot/perp"),
    )
    op.add_column(
        "backtest_results",
        sa.Column("data_source", sa.String(40), nullable=True, comment="K线数据来源"),
    )
    op.add_column(
        "backtest_results",
        sa.Column("leverage", sa.Numeric(10, 2), nullable=True, comment="杠杆倍数（perp）"),
    )
    op.add_column(
        "backtest_results",
        sa.Column(
            "funding_fee_total",
            sa.Numeric(20, 8),
            nullable=True,
            comment="累计资金费用（perp，>0 账户净支付）",
        ),
    )
    op.add_column(
        "backtest_results",
        sa.Column(
            "max_drawdown_duration_hours",
            sa.Numeric(12, 4),
            nullable=True,
            comment="最长回撤水下时长（小时）",
        ),
    )


def downgrade() -> None:
    op.drop_column("backtest_results", "max_drawdown_duration_hours")
    op.drop_column("backtest_results", "funding_fee_total")
    op.drop_column("backtest_results", "leverage")
    op.drop_column("backtest_results", "data_source")
    op.drop_column("backtest_results", "market")
