"""add kline_cache table

Revision ID: 0019
Revises: 0015
Create Date: 2026-05-19

回测加速：避免每次回测都从交易所 REST 拉 5 万根 K 线（60s 超时）。
按 (exchange, symbol, interval, ts) 唯一约束 + 同列复合索引，
让重复回测命中本地缓存秒级返回。

仅写入"已完成 K 线"（ts < now - interval_ms），最后一根可能未收盘的不入缓存。

兼容 SQLite + PostgreSQL：用 SQLAlchemy 通用类型，不用 PG 专用类型。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "kline_cache",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("exchange", sa.String(20), nullable=False),
        sa.Column("symbol", sa.String(40), nullable=False),
        sa.Column(
            "interval",
            sa.String(10),
            nullable=False,
            comment="1m/5m/15m/1h/4h/1d 等",
        ),
        sa.Column(
            "ts",
            sa.BigInteger(),
            nullable=False,
            comment="K线起始时间 epoch 毫秒",
        ),
        sa.Column("open", sa.Numeric(20, 8), nullable=False),
        sa.Column("high", sa.Numeric(20, 8), nullable=False),
        sa.Column("low", sa.Numeric(20, 8), nullable=False),
        sa.Column("close", sa.Numeric(20, 8), nullable=False),
        sa.Column("volume", sa.Numeric(28, 8), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "exchange",
            "symbol",
            "interval",
            "ts",
            name="uq_kline_cache_exchange_symbol_interval_ts",
        ),
    )
    op.create_index(
        "ix_kline_cache_lookup",
        "kline_cache",
        ["exchange", "symbol", "interval", "ts"],
    )


def downgrade() -> None:
    op.drop_index("ix_kline_cache_lookup", table_name="kline_cache")
    op.drop_table("kline_cache")
