"""
数据库迁移: 添加 orders 联合唯一约束 (exchange_order_id, account_id)

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 添加联合唯一约束：不同交易所订单ID可能重复，但同一账户内唯一
    op.create_unique_constraint(
        'uq_order_exchange_account', 'orders',
        ['exchange_order_id', 'account_id'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_order_exchange_account', 'orders', type_='unique')
