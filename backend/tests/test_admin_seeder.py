"""启动时 admin 种子逻辑测试。"""

import pytest
from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.models.user import User


class _FakeSettings:
    """duck-typing：seed_admin 只读 admin_username / admin_password_hash"""

    def __init__(self, username: str, password_hash: str):
        self.admin_username = username
        self.admin_password_hash = password_hash


@pytest.mark.asyncio
async def test_seed_admin_creates_user_when_empty(
    db_session, test_engine_injection, monkeypatch
):
    """users 表为空时，应从 .env 创建 admin。"""
    from app.main import seed_admin

    pwd_hash = hash_password("test-admin-pw")
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: _FakeSettings("admin@example.com", pwd_hash),
    )

    await seed_admin()

    result = await db_session.execute(select(User))
    users = result.scalars().all()
    assert len(users) == 1
    assert users[0].email == "admin@example.com"
    assert verify_password("test-admin-pw", users[0].hashed_password)


@pytest.mark.asyncio
async def test_seed_admin_updates_hash_when_env_changes(
    db_session, test_user, test_engine_injection, monkeypatch
):
    """已有 admin 时，.env 改了密码哈希应同步更新（不新建用户）。"""
    from app.main import seed_admin

    new_hash = hash_password("new-pw-456")
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: _FakeSettings(test_user.email, new_hash),
    )

    await seed_admin()

    # seed_admin 用独立 session 更新；让当前 session 失效以读到最新值
    db_session.expire_all()
    result = await db_session.execute(select(User))
    users = result.scalars().all()
    assert len(users) == 1
    assert verify_password("new-pw-456", users[0].hashed_password)


@pytest.mark.asyncio
async def test_seed_admin_skips_when_hash_empty(
    db_session, test_engine_injection, monkeypatch, caplog
):
    """ADMIN_PASSWORD_HASH 为空时不创建，仅 warning。"""
    import logging

    from app.main import seed_admin

    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: _FakeSettings("admin@example.com", ""),
    )

    with caplog.at_level(logging.WARNING):
        await seed_admin()

    result = await db_session.execute(select(User))
    assert result.scalars().all() == []
    assert any("ADMIN_PASSWORD_HASH" in r.message for r in caplog.records)
