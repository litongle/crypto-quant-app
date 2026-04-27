"""add strategy_instance.state_json

Revision ID: a1b2c3d4e5f6
Revises: d5fb4b2de1b0
Create Date: 2026-04-27 22:30:00.000000

Step 3: 策略状态机持久化 — 重启不丢仓位/极值/cooling_count。
runner 每 tick 末写入 strategy.to_dict(),启动时调 from_dict() 恢复。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "d5fb4b2de1b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """添加 strategy_instances.state_json 列(可空,默认 NULL)。"""
    op.add_column(
        "strategy_instances",
        sa.Column(
            "state_json",
            sa.JSON(),
            nullable=True,
            comment="策略状态机快照 — 重启不丢仓位/极值/cooling_count",
        ),
    )


def downgrade() -> None:
    op.drop_column("strategy_instances", "state_json")
