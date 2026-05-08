"""
数据库迁移: 为策略中心增加工作区状态与生命周期字段

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INSTANCE_WORKSPACE_STATE = sa.Enum(
    "draft",
    "library",
    "running",
    name="instance_workspace_state",
)


def upgrade() -> None:
    bind = op.get_bind()
    INSTANCE_WORKSPACE_STATE.create(bind, checkfirst=True)

    op.add_column(
        "strategy_instances",
        sa.Column(
            "workspace_state",
            INSTANCE_WORKSPACE_STATE,
            nullable=True,
            server_default="library",
            comment="策略中心工作区状态: draft=工作台草稿, library=策略仓库, running=运行台",
        ),
    )
    op.add_column(
        "strategy_instances",
        sa.Column(
            "source_instance_id",
            sa.Integer(),
            nullable=True,
            comment="草稿副本来源的原始策略实例ID",
        ),
    )
    op.add_column(
        "strategy_instances",
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "strategy_instances",
        sa.Column("last_stopped_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        sa.text(
            """
            UPDATE strategy_instances
            SET workspace_state = CASE
                WHEN status = 'running' THEN 'running'
                ELSE 'library'
            END
            """
        )
    )

    op.alter_column("strategy_instances", "workspace_state", nullable=False)
    op.create_index(
        "ix_strategy_instances_workspace_state",
        "strategy_instances",
        ["workspace_state"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_instances_source_instance_id",
        "strategy_instances",
        ["source_instance_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_strategy_instances_source_instance_id_strategy_instances",
        "strategy_instances",
        "strategy_instances",
        ["source_instance_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_strategy_instances_source_instance_id_strategy_instances",
        "strategy_instances",
        type_="foreignkey",
    )
    op.drop_index("ix_strategy_instances_source_instance_id", table_name="strategy_instances")
    op.drop_index("ix_strategy_instances_workspace_state", table_name="strategy_instances")
    op.drop_column("strategy_instances", "last_stopped_at")
    op.drop_column("strategy_instances", "last_started_at")
    op.drop_column("strategy_instances", "source_instance_id")
    op.drop_column("strategy_instances", "workspace_state")
    INSTANCE_WORKSPACE_STATE.drop(op.get_bind(), checkfirst=True)
