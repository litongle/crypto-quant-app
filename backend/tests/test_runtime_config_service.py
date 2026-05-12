"""RuntimeConfigService 行为测试。"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.models.runtime_config import RuntimeConfig
from app.services.runtime_config_service import (
    RuntimeConfigService,
    bootstrap_runtime_config_from_env,
)


@pytest.fixture
def patch_encryption_settings(monkeypatch):
    """让加密模块拿到固定 jwt_secret_key，加解密可重现。"""
    monkeypatch.setattr(
        "app.core.encryption.get_settings",
        lambda: MagicMock(jwt_secret_key="k" * 64),
    )


@pytest.mark.asyncio
async def test_set_then_get_plain(db_session):
    svc = RuntimeConfigService(db_session)
    await svc.set("FOO", "bar", encrypt=False)
    assert await svc.get("FOO") == "bar"


@pytest.mark.asyncio
async def test_set_then_get_encrypted(db_session, patch_encryption_settings):
    svc = RuntimeConfigService(db_session)
    await svc.set("TOKEN", "secret-value", encrypt=True)

    row = (
        await db_session.execute(select(RuntimeConfig).where(RuntimeConfig.key == "TOKEN"))
    ).scalar_one()
    assert row.value != "secret-value"
    assert row.is_encrypted is True

    assert await svc.get("TOKEN") == "secret-value"


@pytest.mark.asyncio
async def test_set_none_deletes_key(db_session):
    svc = RuntimeConfigService(db_session)
    await svc.set("X", "v", encrypt=False)
    await svc.set("X", None, encrypt=False)
    assert await svc.get("X") is None


@pytest.mark.asyncio
async def test_get_missing_returns_none(db_session):
    svc = RuntimeConfigService(db_session)
    assert await svc.get("DOES_NOT_EXIST") is None


@pytest.mark.asyncio
async def test_get_many(db_session, patch_encryption_settings):
    svc = RuntimeConfigService(db_session)
    await svc.set("A", "1", encrypt=False)
    await svc.set("B", "2", encrypt=True)
    assert await svc.get_many(["A", "B", "C"]) == {"A": "1", "B": "2", "C": None}


@pytest.mark.asyncio
async def test_update_overwrites_plain_to_encrypted(db_session, patch_encryption_settings):
    svc = RuntimeConfigService(db_session)
    await svc.set("K", "v1", encrypt=False)
    await svc.set("K", "v2", encrypt=True)
    assert await svc.get("K") == "v2"

    row = (
        await db_session.execute(select(RuntimeConfig).where(RuntimeConfig.key == "K"))
    ).scalar_one()
    assert row.is_encrypted is True


@pytest.mark.asyncio
async def test_bootstrap_fills_only_missing(db_session, monkeypatch, patch_encryption_settings):
    svc = RuntimeConfigService(db_session)
    await svc.set("TELEGRAM_CHAT_ID", "existing", encrypt=False)

    mock_settings = MagicMock(
        telegram_bot_token="env_token",
        telegram_chat_id="env_chat",
        smtp_host=None,
        smtp_port=465,
        smtp_username=None,
        smtp_password=None,
        smtp_from=None,
        smtp_to=None,
        smtp_use_tls=True,
        auto_pause_consecutive_errors=5,
        auto_pause_consecutive_order_failures=3,
        auto_pause_heartbeat_multiplier=5,
        auto_pause_heartbeat_min_seconds=300,
        auto_pause_watchdog_interval_seconds=30,
    )
    monkeypatch.setattr("app.services.runtime_config_service.get_settings", lambda: mock_settings)

    await bootstrap_runtime_config_from_env(db_session)

    assert await svc.get("TELEGRAM_CHAT_ID") == "existing"  # 未覆盖
    assert await svc.get("TELEGRAM_BOT_TOKEN") == "env_token"  # 新填
    assert await svc.get("SMTP_HOST") is None  # env 也没值
    assert await svc.get("AUTO_PAUSE_CONSECUTIVE_ERRORS") == "5"
    assert await svc.get("SMTP_USE_TLS") == "True"
