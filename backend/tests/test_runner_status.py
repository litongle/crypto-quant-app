"""runner/status 端点关键设置字段切换数据源的回归测试。"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.runtime_config_service import RuntimeConfigService


@pytest.fixture
def patch_encryption_settings(monkeypatch):
    monkeypatch.setattr(
        "app.core.encryption.get_settings",
        lambda: MagicMock(jwt_secret_key="k" * 64),
    )


@pytest.fixture(autouse=True)
def patch_exchange_ping(monkeypatch):
    """mock 掉交易所连通性探测，避免单测里真的去连 binance/okx/huobi。"""
    client = MagicMock()
    client.ping = AsyncMock()
    client.get_ticker = AsyncMock()
    monkeypatch.setattr("app.api.v1.strategies.get_exchange_adapter", lambda *a, **kw: client)


@pytest.mark.asyncio
async def test_runner_status_reads_from_runtime_config(
    client, db_session, auth_headers, patch_encryption_settings
):
    await RuntimeConfigService(db_session).set("TELEGRAM_BOT_TOKEN", "x", encrypt=True)
    await RuntimeConfigService(db_session).set("AUTO_PAUSE_CONSECUTIVE_ERRORS", "9", encrypt=False)

    resp = await client.get("/api/v1/strategies/runner/status", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["settings"]["notifications"]["telegram_bot_token_configured"] is True
    assert body["settings"]["notifications"]["telegram_chat_id_configured"] is False
    assert body["settings"]["auto_pause"]["consecutive_errors"] == 9


@pytest.mark.asyncio
async def test_runner_status_uses_defaults_when_runtime_empty(client, auth_headers):
    resp = await client.get("/api/v1/strategies/runner/status", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    # 未配置时与 .env.example 默认对齐
    assert body["settings"]["auto_pause"]["consecutive_errors"] == 5
    assert body["settings"]["auto_pause"]["watchdog_interval_seconds"] == 30
    assert body["settings"]["notifications"]["telegram_bot_token_configured"] is False
