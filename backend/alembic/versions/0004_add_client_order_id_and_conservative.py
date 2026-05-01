"""
数据库迁移: 添加 orders.client_order_id + strategy_risk_level 加 conservative

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 添加 orders.client_order_id（幂等订单ID，防止超时重试导致重复下单）
    op.add_column('orders', sa.Column(
        'client_order_id', sa.String(64), nullable=True,
        comment='客户端幂等订单ID',
    ))
    op.create_index('ix_orders_client_order_id', 'orders', ['client_order_id'])

    # 2. strategy_risk_level enum 添加 conservative 值
    # PostgreSQL 不能直接 ALTER TYPE ADD VALUE 在事务内，需用 COMMIT
    op.execute("ALTER TYPE strategy_risk_level ADD VALUE IF NOT EXISTS 'conservative'")


def downgrade() -> None:
    op.drop_index('ix_orders_client_order_id', table_name='orders')
    op.drop_column('orders', 'client_order_id')
    # 注意: PostgreSQL 不支持从 enum 中移除值，downgrade 不处理 conservative
