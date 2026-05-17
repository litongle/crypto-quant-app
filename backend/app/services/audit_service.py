"""审计事件写入服务 — 把 risk_alert / user_action / system 这些
没有业务表的事件统一落到 audit_events 表，便于后端事件流串起来。

设计原则：
- 写失败不抛 — 审计是 best-effort 副作用，不能让主流程为它崩溃。
- 不更新 — 这是 append-only 表，新事件追加，不允许 update。
- 上下文字段都可选 — 系统启动事件没有 user_id，告警可能没有 instance_id。
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent

logger = logging.getLogger(__name__)


Severity = str  # "info" | "warning" | "error" | "critical"
EventKind = str  # "risk_alert" | "user_action" | "system"


async def _write(
    session: AsyncSession,
    *,
    kind: EventKind,
    summary: str,
    severity: Severity = "info",
    user_id: int | None = None,
    instance_id: int | None = None,
    account_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent | None:
    """直接给定 session 时使用 — 调用方负责 commit（让事件与业务变更同 commit）。"""
    try:
        event = AuditEvent(
            type=kind,
            severity=severity,
            user_id=user_id,
            instance_id=instance_id,
            account_id=account_id,
            summary=summary[:200],
            detail=detail,
        )
        session.add(event)
        await session.flush()
        return event
    except Exception as exc:
        logger.warning("[AuditService] 写入事件失败 type=%s: %s", kind, exc)
        return None


async def write_with_session_maker(
    session_maker,
    *,
    kind: EventKind,
    summary: str,
    severity: Severity = "info",
    user_id: int | None = None,
    instance_id: int | None = None,
    account_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """没有 session 时使用 — 自己开 session 并 commit。失败不抛。

    适用场景：strategy_runner / notification_service 这类不在 HTTP 请求里的写入点。
    """
    if session_maker is None:
        return
    try:
        async with session_maker() as session:
            await _write(
                session,
                kind=kind,
                summary=summary,
                severity=severity,
                user_id=user_id,
                instance_id=instance_id,
                account_id=account_id,
                detail=detail,
            )
            await session.commit()
    except Exception as exc:
        logger.warning("[AuditService] 写入事件失败 kind=%s: %s", kind, exc)


# 便捷方法 — 按事件类型预设
async def log_risk_alert(
    session_maker,
    *,
    alert_type: str,
    message: str,
    severity: Severity = "warning",
    instance_id: int | None = None,
    account_id: int | None = None,
    metrics: dict[str, Any] | None = None,
) -> None:
    """记录风控告警事件。与 notify_risk_alert 配套 — 一个发通知，一个落库。"""
    detail: dict[str, Any] = {"alert_type": alert_type, "message": message}
    if metrics:
        detail["metrics"] = metrics
    summary = f"风控告警 · {alert_type} · {message}"
    await write_with_session_maker(
        session_maker,
        kind="risk_alert",
        summary=summary,
        severity=severity,
        instance_id=instance_id,
        account_id=account_id,
        detail=detail,
    )


async def log_user_action(
    session,
    *,
    action: str,
    user_id: int,
    summary: str,
    instance_id: int | None = None,
    account_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """记录用户操作 — 直接给 session（让审计与业务变更同一事务）。"""
    merged_detail = {"action": action, **(detail or {})}
    await _write(
        session,
        kind="user_action",
        summary=summary,
        severity="info",
        user_id=user_id,
        instance_id=instance_id,
        account_id=account_id,
        detail=merged_detail,
    )


async def log_system(
    session_maker,
    *,
    event: str,
    summary: str,
    severity: Severity = "info",
    detail: dict[str, Any] | None = None,
) -> None:
    """记录系统事件（应用启动/停止/调度器启动等）。"""
    merged_detail = {"event": event, **(detail or {})}
    await write_with_session_maker(
        session_maker,
        kind="system",
        summary=summary,
        severity=severity,
        detail=merged_detail,
    )


async def log_auto_pause(
    session_maker,
    *,
    instance_id: int,
    instance_name: str,
    reason: str,
    detail_text: str,
    severity: Severity = "warning",
    metrics: dict[str, Any] | None = None,
) -> None:
    """记录策略自停事件。

    与 risk_alert 区分：risk_alert 是"告警通知"（推 Telegram/邮件），auto_pause
    是"业务事件"（策略状态机迁移）。两者用途不同：前者侧重 ops，后者侧重审计。

    与 strategy_instance.last_pause_reason 字段区分：字段记的是"当前最近一次"
    暂停原因（启动后清除），audit_events.auto_pause 记的是"全部历史"暂停事件
    （append-only,不被覆盖）。
    """
    merged_detail: dict[str, Any] = {
        "instance_name": instance_name,
        "reason": reason,
        "message": detail_text,
    }
    if metrics:
        merged_detail["metrics"] = metrics
    summary = f"{instance_name} 自动暂停 · {detail_text}"
    await write_with_session_maker(
        session_maker,
        kind="auto_pause",
        summary=summary,
        severity=severity,
        instance_id=instance_id,
        detail=merged_detail,
    )
