"""设置 API 端点测试 — 通知 + SMTP + 测试发送。"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.runtime_config_service import RuntimeConfigService


@pytest.fixture
def patch_encryption_settings(monkeypatch):
    monkeypatch.setattr(
        "app.core.encryption.get_settings",
        lambda: MagicMock(jwt_secret_key="k" * 64),
    )


@pytest.mark.asyncio
async def test_get_notifications_returns_mask_when_set(
    client, db_session, auth_headers, patch_encryption_settings
):
    svc = RuntimeConfigService(db_session)
    await svc.set("TELEGRAM_BOT_TOKEN", "real-token-abc", encrypt=True)
    await svc.set("TELEGRAM_CHAT_ID", "12345", encrypt=False)

    resp = await client.get("/api/v1/settings/notifications", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["telegram_bot_token"] == "••••••"
    assert body["telegram_bot_token_is_set"] is True
    assert body["telegram_chat_id"] == "12345"


@pytest.mark.asyncio
async def test_get_notifications_empty(client, auth_headers):
    resp = await client.get("/api/v1/settings/notifications", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["telegram_bot_token_is_set"] is False
    assert body["telegram_chat_id"] in (None, "")


@pytest.mark.asyncio
async def test_put_notifications_writes_token(
    client, db_session, auth_headers, patch_encryption_settings
):
    resp = await client.put(
        "/api/v1/settings/notifications",
        json={"telegram_bot_token": "new-token", "telegram_chat_id": "999"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert await RuntimeConfigService(db_session).get("TELEGRAM_BOT_TOKEN") == "new-token"
    assert await RuntimeConfigService(db_session).get("TELEGRAM_CHAT_ID") == "999"


@pytest.mark.asyncio
async def test_put_notifications_null_preserves_existing(
    client, db_session, auth_headers, patch_encryption_settings
):
    await RuntimeConfigService(db_session).set("TELEGRAM_BOT_TOKEN", "existing", encrypt=True)
    resp = await client.put(
        "/api/v1/settings/notifications",
        json={"telegram_bot_token": None, "telegram_chat_id": "777"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert await RuntimeConfigService(db_session).get("TELEGRAM_BOT_TOKEN") == "existing"


@pytest.mark.asyncio
async def test_put_notifications_empty_string_clears(
    client, db_session, auth_headers, patch_encryption_settings
):
    await RuntimeConfigService(db_session).set("TELEGRAM_BOT_TOKEN", "existing", encrypt=True)
    resp = await client.put(
        "/api/v1/settings/notifications",
        json={"telegram_bot_token": "", "telegram_chat_id": None},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert await RuntimeConfigService(db_session).get("TELEGRAM_BOT_TOKEN") is None


@pytest.mark.asyncio
async def test_smtp_get_and_put(client, db_session, auth_headers, patch_encryption_settings):
    resp = await client.put(
        "/api/v1/settings/smtp",
        json={
            "smtp_host": "smtp.qq.com",
            "smtp_port": 465,
            "smtp_username": "u@qq.com",
            "smtp_password": "auth-code",
            "smtp_from": None,
            "smtp_to": "me@example.com",
            "smtp_use_tls": True,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = await client.get("/api/v1/settings/smtp", headers=auth_headers)
    body = resp.json()
    assert body["smtp_host"] == "smtp.qq.com"
    assert body["smtp_port"] == 465
    assert body["smtp_password"] == "••••••"
    assert body["smtp_password_is_set"] is True
    assert body["smtp_use_tls"] is True


@pytest.mark.asyncio
async def test_notifications_test_endpoint_telegram(
    client, db_session, auth_headers, monkeypatch, patch_encryption_settings
):
    sent = AsyncMock()
    monkeypatch.setattr(
        "app.services.notification_service.NotificationService._send_telegram", sent
    )
    await RuntimeConfigService(db_session).set("TELEGRAM_BOT_TOKEN", "t", encrypt=True)
    await RuntimeConfigService(db_session).set("TELEGRAM_CHAT_ID", "c", encrypt=False)

    resp = await client.post(
        "/api/v1/settings/notifications/test",
        json={"channel": "telegram"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    sent.assert_awaited_once()


@pytest.mark.asyncio
async def test_notifications_test_endpoint_returns_502_on_failure(
    client, db_session, auth_headers, monkeypatch, patch_encryption_settings
):
    monkeypatch.setattr(
        "app.services.notification_service.NotificationService._send_telegram",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    await RuntimeConfigService(db_session).set("TELEGRAM_BOT_TOKEN", "t", encrypt=True)
    await RuntimeConfigService(db_session).set("TELEGRAM_CHAT_ID", "c", encrypt=False)

    resp = await client.post(
        "/api/v1/settings/notifications/test",
        json={"channel": "telegram"},
        headers=auth_headers,
    )
    assert resp.status_code == 502
    assert "boom" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(client):
    resp = await client.get("/api/v1/settings/notifications")
    assert resp.status_code in (401, 403)


# ── risk 风控阈值 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_risk_returns_defaults_when_empty(client, auth_headers):
    resp = await client.get("/api/v1/settings/risk", headers=auth_headers)
    body = resp.json()
    assert resp.status_code == 200, resp.text
    assert body["consecutive_errors"] == 5
    assert body["consecutive_order_failures"] == 3
    assert body["heartbeat_multiplier"] == 5
    assert body["heartbeat_min_seconds"] == 300
    assert body["watchdog_interval_seconds"] == 30


@pytest.mark.asyncio
async def test_put_risk_writes_values(client, db_session, auth_headers):
    resp = await client.put(
        "/api/v1/settings/risk",
        json={
            "consecutive_errors": 10,
            "consecutive_order_failures": 4,
            "heartbeat_multiplier": 6,
            "heartbeat_min_seconds": 600,
            "watchdog_interval_seconds": 60,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["consecutive_errors"] == 10
    assert await RuntimeConfigService(db_session).get("AUTO_PAUSE_CONSECUTIVE_ERRORS") == "10"


@pytest.mark.asyncio
async def test_put_risk_rejects_out_of_range(client, auth_headers):
    resp = await client.put(
        "/api/v1/settings/risk",
        json={
            "consecutive_errors": 0,  # 必须 >= 1
            "consecutive_order_failures": 1,
            "heartbeat_multiplier": 1,
            "heartbeat_min_seconds": 10,
            "watchdog_interval_seconds": 5,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422
