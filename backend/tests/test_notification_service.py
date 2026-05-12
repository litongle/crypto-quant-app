"""通知服务测试 — 重点验证从 runtime_config 读取后的渠道分发逻辑。"""

from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def fresh_service(monkeypatch):
    """每次给一份干净的 NotificationService 实例，并 mock 出 _load_config 桩。

    桩值用 runtime_config 的 key 命名 + 字符串值（与生产从 DB 读出来的一致）。
    """
    from app.services.notification_service import NotificationService

    svc = NotificationService()

    def _set_config(**overrides):
        defaults: dict[str, str | None] = {
            "TELEGRAM_BOT_TOKEN": None,
            "TELEGRAM_CHAT_ID": None,
            "SMTP_HOST": None,
            "SMTP_PORT": "465",
            "SMTP_USERNAME": None,
            "SMTP_PASSWORD": None,
            "SMTP_FROM": None,
            "SMTP_TO": None,
            "SMTP_USE_TLS": "true",
        }
        defaults.update(overrides)

        async def fake_load():
            return defaults

        svc._load_config = fake_load  # type: ignore[method-assign]
        return svc

    return _set_config


@pytest.mark.asyncio
async def test_send_skips_email_when_config_incomplete(fresh_service, monkeypatch):
    """SMTP 任一字段缺失 → 不调用 aiosmtplib"""
    svc = fresh_service(SMTP_HOST="smtp.qq.com", SMTP_USERNAME="x@y.com")  # 缺 password/to

    send_mock = AsyncMock()
    monkeypatch.setattr("app.services.notification_service.aiosmtplib.send", send_mock)

    result = await svc._send("标题", "正文", "system")

    send_mock.assert_not_awaited()
    assert result["email"] is False


@pytest.mark.asyncio
async def test_send_email_when_fully_configured(fresh_service, monkeypatch):
    """SMTP 配置齐全 → 调用 aiosmtplib.send 一次，参数正确"""
    svc = fresh_service(
        SMTP_HOST="smtp.qq.com",
        SMTP_PORT="465",
        SMTP_USERNAME="user@qq.com",
        SMTP_PASSWORD="auth_code_abc",
        SMTP_TO="me@example.com",
    )

    send_mock = AsyncMock()
    monkeypatch.setattr("app.services.notification_service.aiosmtplib.send", send_mock)

    result = await svc._send("策略崩溃", "策略 #42 异常退出: RuntimeError", "risk_alert")

    assert result["email"] is True
    send_mock.assert_awaited_once()

    call_args = send_mock.call_args
    msg = call_args.args[0]
    assert msg["Subject"] == "[CryptoQuant] 策略崩溃"
    assert msg["From"] == "user@qq.com"  # SMTP_FROM 未填，回退到 username
    assert msg["To"] == "me@example.com"
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
    """SMTP_FROM 显式设置时应优先于 SMTP_USERNAME"""
    svc = fresh_service(
        SMTP_HOST="smtp.163.com",
        SMTP_USERNAME="alerts_account@163.com",
        SMTP_PASSWORD="x",
        SMTP_FROM="CryptoQuant Alerts <alerts@mydomain.com>",
        SMTP_TO="me@example.com",
    )

    send_mock = AsyncMock()
    monkeypatch.setattr("app.services.notification_service.aiosmtplib.send", send_mock)

    await svc._send("t", "m", "system")

    msg = send_mock.call_args.args[0]
    assert "alerts@mydomain.com" in msg["From"]


@pytest.mark.asyncio
async def test_send_email_starttls_for_port_587(fresh_service, monkeypatch):
    """SMTP_USE_TLS=false 时应走 STARTTLS（587 端口典型场景）"""
    svc = fresh_service(
        SMTP_HOST="smtp.example.com",
        SMTP_PORT="587",
        SMTP_USERNAME="x",
        SMTP_PASSWORD="y",
        SMTP_TO="z@example.com",
        SMTP_USE_TLS="false",
    )

    send_mock = AsyncMock()
    monkeypatch.setattr("app.services.notification_service.aiosmtplib.send", send_mock)

    await svc._send("t", "m", "system")

    kwargs = send_mock.call_args.kwargs
    assert kwargs["use_tls"] is False
    assert kwargs["start_tls"] is True
    assert kwargs["port"] == 587


@pytest.mark.asyncio
async def test_send_swallows_email_failure(fresh_service, monkeypatch):
    """邮件发送异常被吞，错误记入 errors，但不影响其他渠道结果"""
    svc = fresh_service(
        SMTP_HOST="smtp.qq.com",
        SMTP_USERNAME="x@y.com",
        SMTP_PASSWORD="x",
        SMTP_TO="me@example.com",
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


@pytest.mark.asyncio
async def test_send_telegram_when_configured(fresh_service, monkeypatch):
    """Telegram 配置齐全 → 调用 _send_telegram；不应触碰 SMTP"""
    svc = fresh_service(
        TELEGRAM_BOT_TOKEN="bot_token_xyz",
        TELEGRAM_CHAT_ID="chat_abc",
    )

    tg_mock = AsyncMock()
    monkeypatch.setattr(svc, "_send_telegram", tg_mock)

    result = await svc._send("t", "m", "system")

    assert result["telegram"] is True
    tg_mock.assert_awaited_once()
    args = tg_mock.call_args.args
    assert args[1] == "bot_token_xyz"
    assert args[2] == "chat_abc"
