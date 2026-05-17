"""backfill historical last_pause_reason into audit_events

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-17

auto_pause 事件从「strategy_instances.last_pause_reason 字段派生」改成「audit_events
表的 type=auto_pause 行」(本次改动)。但 last_pause_reason 是字段，启动后会被清除,
历史多次暂停只保留最后一次。

回填策略：遍历当前 last_pause_reason IS NOT NULL 的实例，把它（仅最近一次）写入
audit_events。已经被清除的更早历史无法恢复（数据已丢失）。本环境 0 行也没事。
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_REASON_LABEL = {
    "auto:heartbeat_timeout": "心跳超时",
    "auto:consecutive_errors": "连续错误",
    "auto:order_failures": "下单失败次数过多",
    "auto:state_drift": "持仓状态漂移",
    "auto:unknown": "未知原因",
}


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, user_id, name, last_pause_reason, last_stopped_at
              FROM strategy_instances
             WHERE last_pause_reason IS NOT NULL
            """
        )
    ).fetchall()

    for row in rows:
        inst_id, user_id, name, reason, stopped_at = row
        label = _REASON_LABEL.get(reason, reason)
        severity = "critical" if reason == "auto:state_drift" else "warning"
        summary = f'{name or "策略"} 自动暂停 · {label}'[:200]
        detail_json = json.dumps(
            {
                "reason": reason,
                "instance_name": name or "",
                "backfilled": True,
            },
            ensure_ascii=False,
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO audit_events
                    (type, severity, user_id, instance_id, summary, detail, created_at)
                VALUES
                    (:type, :severity, :user_id, :instance_id, :summary,
                     CAST(:detail AS json), COALESCE(:created_at, NOW()))
                """
            ),
            {
                "type": "auto_pause",
                "severity": severity,
                "user_id": user_id,
                "instance_id": inst_id,
                "summary": summary,
                "detail": detail_json,
                "created_at": stopped_at,
            },
        )


def downgrade() -> None:
    # 回填记录用 detail.backfilled=true 标识，可按此清理
    op.execute(
        """
        DELETE FROM audit_events
         WHERE type = 'auto_pause'
           AND (detail::jsonb ->> 'backfilled') = 'true'
        """
    )
