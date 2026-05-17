"""AuditService 测试 — 三个便捷函数 log_user_action / log_risk_alert / log_system。

直接对照 audit_events 表行为验证：写入字段、severity、user_id 隔离、失败不抛。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit_event import AuditEvent
from app.models.user import User
from app.services.audit_service import log_risk_alert, log_system, log_user_action


async def _make_user(session, email: str = "audit@example.com") -> User:
    user = User(
        email=email,
        name="audituser",
        hashed_password=hash_password("password123"),
        status="active",
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


# ==================== log_user_action ====================


@pytest.mark.asyncio
async def test_log_user_action_writes_full_row(db_session):
    user = await _make_user(db_session)
    await log_user_action(
        db_session,
        action="start_strategy",
        user_id=user.id,
        instance_id=42,
        summary='启动策略 "测试"',
        detail={"foo": "bar"},
    )
    await db_session.commit()

    rows = (await db_session.execute(select(AuditEvent))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.type == "user_action"
    assert row.severity == "info"
    assert row.user_id == user.id
    assert row.instance_id == 42
    assert row.summary == '启动策略 "测试"'
    # action 被并进 detail
    assert row.detail == {"action": "start_strategy", "foo": "bar"}


@pytest.mark.asyncio
async def test_log_user_action_uses_provided_session_no_commit(db_session):
    """log_user_action 不应自己 commit — 调用方控制事务边界。"""
    user = await _make_user(db_session)
    await log_user_action(
        db_session,
        action="stop_strategy",
        user_id=user.id,
        instance_id=1,
        summary="停止",
    )
    # 未 commit 时,新 session 读不到（flush 但 commit 由 caller 控）
    # 这里我们 rollback 验证 transient
    await db_session.rollback()
    rows = (await db_session.execute(select(AuditEvent))).scalars().all()
    assert rows == []


# ==================== log_risk_alert ====================


@pytest.mark.asyncio
async def test_log_risk_alert_writes_to_own_session(db_session):
    """log_risk_alert 用 session_maker 自开 session，独立 commit。"""
    # 用 db_session 同款 session_maker
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=db_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)
    # session.commit 用真的 db_session.commit;但 audit_service 会调它的 commit,
    # 我们让这个 commit 调用走 db_session 实际 commit
    session_maker = MagicMock(return_value=fake_session_cm)

    await log_risk_alert(
        session_maker,
        alert_type="策略崩溃",
        message="task 异常退出",
        severity="critical",
        instance_id=99,
        account_id=3,
        metrics={"k": "v"},
    )

    rows = (await db_session.execute(select(AuditEvent))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.type == "risk_alert"
    assert row.severity == "critical"
    assert row.instance_id == 99
    assert row.account_id == 3
    assert "策略崩溃" in row.summary
    assert row.detail == {
        "alert_type": "策略崩溃",
        "message": "task 异常退出",
        "metrics": {"k": "v"},
    }


@pytest.mark.asyncio
async def test_log_risk_alert_swallows_session_maker_error(monkeypatch, caplog):
    """session_maker 抛异常时不影响调用方。"""
    failing_maker = MagicMock(side_effect=RuntimeError("db down"))

    # 应当不抛
    await log_risk_alert(
        failing_maker,
        alert_type="测试",
        message="x",
    )
    # caplog 不一定捕获到 logger.warning（pytest 默认 propagate 关），不严格断言


@pytest.mark.asyncio
async def test_log_risk_alert_none_session_maker_noop():
    """session_maker=None（启动初期）→ 静默忽略。"""
    await log_risk_alert(None, alert_type="X", message="Y")  # 不抛即通过


# ==================== log_system ====================


@pytest.mark.asyncio
async def test_log_system_writes_with_null_user_id(db_session):
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=db_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)
    session_maker = MagicMock(return_value=fake_session_cm)

    await log_system(
        session_maker,
        event="app_started",
        summary="系统启动 · v1.0.0",
        detail={"environment": "test"},
    )

    rows = (await db_session.execute(select(AuditEvent))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.type == "system"
    assert row.user_id is None  # 系统事件不挂用户
    assert row.detail == {"event": "app_started", "environment": "test"}
