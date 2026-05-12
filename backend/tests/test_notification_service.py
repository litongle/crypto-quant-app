"""通知服务测试 — 重点验证邮箱适配（Telegram 在生产中验证）。"""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def fresh_service(monkeypatch):
    """每次给一份干净的 NotificationService 实例，并 mock 出 settings 桩。"""
    from app.services.notification_service import NotificationService

    svc = NotificationService()

    def _set_settings(**overrides):
        defaults = {
            "telegram_bot_token": None,
            "telegram_chat_id": None,
            "smtp_host": None,
            "smtp_port": 465,
            "smtp_username": None,
            "smtp_password": None,
            "smtp_from": None,
            "smtp_to": None,
            "smtp_use_tls": True,
        }
        defaults.update(overrides)
        svc._settings = MagicMock(**defaults)
        return svc

    return _set_settings


@pytest.mark.asyncio
async def test_send_skips_email_when_config_incomplete(fresh_service, monkeypatch):
    """SMTP 任一字段缺失 → 不调用 aiosmtplib"""
    svc = fresh_service(smtp_host="smtp.qq.com", smtp_username="x@y.com")  # 缺 password/to

    send_mock = AsyncMock()
    monkeypatch.setattr("app.services.notification_service.aiosmtplib.send", send_mock)

    result = await svc._send("标题", "正文", "system")

    send_mock.assert_not_awaited()
    assert result["email"] is False


@pytest.mark.asyncio
async def test_send_email_when_fully_configured(fresh_service, monkeypatch):
    """SMTP 配置齐全 → 调用 aiosmtplib.send 一次，参数正确"""
    svc = fresh_service(
        smtp_host="smtp.qq.com",
        smtp_port=465,
        smtp_username="user@qq.com",
        smtp_password="auth_code_abc",
        smtp_to="me@example.com",
    )

    send_mock = AsyncMock()
    monkeypatch.setattr("app.services.notification_service.aiosmtplib.send", send_mock)

    result = await svc._send("策略崩溃", "策略 #42 异常退出: RuntimeError", "risk_alert")

    assert result["email"] is True
    send_mock.assert_awaited_once()

    call_args = send_mock.call_args
    msg = call_args.args[0]
    assert msg["Subject"] == "[CryptoQuant] 策略崩溃"
    assert msg["From"] == "user@qq.com"  # smtp_from 未填，回退到 username
    assert msg["To"] == "me@example.com"
    # 正文应包含 message
    body = msg.get_body(preferencelist=("plain",))
    assert "策略 #42" in body.get_content()

    kwargs = call_args.kwargs
    assert kwargs["hostname"] == "smtp.qq.com"
    assert kwargs["port"] == 465
    assert kwargs["username"] == "user@qq.com"
    assert kwargs["password"] == "auth_code_abc"
    assert kwargs["use_tls"] is True
    assert kwargs["start_tls"] is False


@pytest.mark.asyncio
async def test_send_email_uses_smtp_from_when_set(fresh_service, monkeypatch):
    """smtp_from 显式设置时应优先于 smtp_username"""
    svc = fresh_service(
        smtp_host="smtp.163.com",
        smtp_username="alerts_account@163.com",
        smtp_password="x",
        smtp_from="CryptoQuant Alerts <alerts@mydomain.com>",
        smtp_to="me@example.com",
    )

    send_mock = AsyncMock()
    monkeypatch.setattr("app.services.notification_service.aiosmtplib.send", send_mock)

    await svc._send("t", "m", "system")

    msg = send_mock.call_args.args[0]
    assert "alerts@mydomain.com" in msg["From"]


@pytest.mark.asyncio
async def test_send_email_starttls_for_port_587(fresh_service, monkeypatch):
    """smtp_use_tls=False 时应走 STARTTLS（587 端口典型场景）"""
    svc = fresh_service(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="x",
        smtp_password="y",
        smtp_to="z@example.com",
        smtp_use_tls=False,
    )

    send_mock = AsyncMock()
    monkeypatch.setattr("app.services.notification_service.aiosmtplib.send", send_mock)

    await svc._send("t", "m", "system")

    kwargs = send_mock.call_args.kwargs
    assert kwargs["use_tls"] is False
    assert kwargs["start_tls"] is True


@pytest.mark.asyncio
async def test_send_swallows_email_failure(fresh_service, monkeypatch):
    """邮件发送异常被吞，错误记入 errors，但不影响其他渠道结果"""
    svc = fresh_service(
        smtp_host="smtp.qq.com",
        smtp_username="x@y.com",
        smtp_password="x",
        smtp_to="me@example.com",
    )

    send_mock = AsyncMock(side_effect=RuntimeError("connection refused"))
    monkeypatch.setattr("app.services.notification_service.aiosmtplib.send", send_mock)

    result = await svc._send("t", "m", "system")

    assert result["email"] is False
    assert any("connection refused" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_send_no_channel_configured_logs_only(fresh_service, monkeypatch, caplog):
    """所有渠道都未配 → 仅 logger 记录，无异常"""
    import logging

    svc = fresh_service()  # 全部默认 None

    send_mock = AsyncMock()
    monkeypatch.setattr("app.services.notification_service.aiosmtplib.send", send_mock)

    with caplog.at_level(logging.INFO, logger="app.services.notification_service"):
        result = await svc._send("无渠道测试", "正文", "system")

    assert result == {"telegram": False, "email": False, "errors": []}
    send_mock.assert_not_awaited()
    assert any("未配置通知渠道" in r.message for r in caplog.records)
