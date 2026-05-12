"""前端可改的运行时设置 — 通知通道（Telegram / SMTP）+ 风控阈值 + 测试发送。"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.services.notification_service import NotificationService
from app.services.runtime_config_service import RuntimeConfigService

router = APIRouter(prefix="/settings", tags=["settings"])
MASK = "••••••"


# ── Schema ────────────────────────────────────────────────────


class NotificationsIn(BaseModel):
    """None=不修改；""=清空；其他字符串=覆盖。"""

    model_config = ConfigDict(extra="forbid")

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None


class NotificationsOut(BaseModel):
    telegram_bot_token: str | None
    telegram_bot_token_is_set: bool
    telegram_chat_id: str | None


class SmtpIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None  # None=不变；""=清空；其他=覆盖
    smtp_from: str | None = None
    smtp_to: str | None = None
    smtp_use_tls: bool | None = None


class SmtpOut(BaseModel):
    smtp_host: str | None
    smtp_port: int | None
    smtp_username: str | None
    smtp_password: str | None
    smtp_password_is_set: bool
    smtp_from: str | None
    smtp_to: str | None
    smtp_use_tls: bool | None


class TestIn(BaseModel):
    channel: Literal["telegram", "email"]


class RiskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consecutive_errors: int = Field(ge=1, le=100)
    consecutive_order_failures: int = Field(ge=1, le=100)
    heartbeat_multiplier: int = Field(ge=1, le=100)
    heartbeat_min_seconds: int = Field(ge=10, le=3600)
    watchdog_interval_seconds: int = Field(ge=5, le=600)


class RiskOut(BaseModel):
    consecutive_errors: int
    consecutive_order_failures: int
    heartbeat_multiplier: int
    heartbeat_min_seconds: int
    watchdog_interval_seconds: int


# ── 工具 ──────────────────────────────────────────────────────


async def _put_secret(svc: RuntimeConfigService, key: str, value: str | None, *, encrypt: bool):
    """None=不变；""=清空；其他=覆盖。"""
    if value is None:
        return
    if value == "":
        await svc.set(key, None, encrypt=encrypt)
    else:
        await svc.set(key, value, encrypt=encrypt)


async def _put_plain(svc: RuntimeConfigService, key: str, value: str | None):
    """None=不变；""=清空；其他=覆盖（明文）。"""
    if value is None:
        return
    if value == "":
        await svc.set(key, None, encrypt=False)
    else:
        await svc.set(key, value, encrypt=False)


# ── 通知通道（Telegram）────────────────────────────────────────


@router.get(
    "/notifications",
    response_model=NotificationsOut,
    dependencies=[Depends(get_current_user)],
)
async def get_notifications(db: AsyncSession = Depends(get_db)):
    cfg = await RuntimeConfigService(db).get_many(["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])
    return NotificationsOut(
        telegram_bot_token=MASK if cfg["TELEGRAM_BOT_TOKEN"] else None,
        telegram_bot_token_is_set=bool(cfg["TELEGRAM_BOT_TOKEN"]),
        telegram_chat_id=cfg["TELEGRAM_CHAT_ID"],
    )


@router.put(
    "/notifications",
    response_model=NotificationsOut,
    dependencies=[Depends(get_current_user)],
)
async def put_notifications(body: NotificationsIn, db: AsyncSession = Depends(get_db)):
    svc = RuntimeConfigService(db)
    await _put_secret(svc, "TELEGRAM_BOT_TOKEN", body.telegram_bot_token, encrypt=True)
    await _put_plain(svc, "TELEGRAM_CHAT_ID", body.telegram_chat_id)
    return await get_notifications(db=db)


# ── 邮箱 SMTP ────────────────────────────────────────────────


@router.get(
    "/smtp",
    response_model=SmtpOut,
    dependencies=[Depends(get_current_user)],
)
async def get_smtp(db: AsyncSession = Depends(get_db)):
    cfg = await RuntimeConfigService(db).get_many(
        [
            "SMTP_HOST",
            "SMTP_PORT",
            "SMTP_USERNAME",
            "SMTP_PASSWORD",
            "SMTP_FROM",
            "SMTP_TO",
            "SMTP_USE_TLS",
        ]
    )
    use_tls = cfg["SMTP_USE_TLS"]
    return SmtpOut(
        smtp_host=cfg["SMTP_HOST"],
        smtp_port=int(cfg["SMTP_PORT"]) if cfg["SMTP_PORT"] else None,
        smtp_username=cfg["SMTP_USERNAME"],
        smtp_password=MASK if cfg["SMTP_PASSWORD"] else None,
        smtp_password_is_set=bool(cfg["SMTP_PASSWORD"]),
        smtp_from=cfg["SMTP_FROM"],
        smtp_to=cfg["SMTP_TO"],
        smtp_use_tls=(str(use_tls).lower() == "true") if use_tls is not None else None,
    )


@router.put(
    "/smtp",
    response_model=SmtpOut,
    dependencies=[Depends(get_current_user)],
)
async def put_smtp(body: SmtpIn, db: AsyncSession = Depends(get_db)):
    svc = RuntimeConfigService(db)
    await _put_plain(svc, "SMTP_HOST", body.smtp_host)
    await _put_plain(svc, "SMTP_USERNAME", body.smtp_username)
    await _put_plain(svc, "SMTP_FROM", body.smtp_from)
    await _put_plain(svc, "SMTP_TO", body.smtp_to)
    if body.smtp_port is not None:
        await svc.set("SMTP_PORT", str(body.smtp_port), encrypt=False)
    if body.smtp_use_tls is not None:
        await svc.set("SMTP_USE_TLS", "true" if body.smtp_use_tls else "false", encrypt=False)
    await _put_secret(svc, "SMTP_PASSWORD", body.smtp_password, encrypt=True)
    return await get_smtp(db=db)


# ── 风控阈值 ──────────────────────────────────────────────────


_RISK_KEYS_DEFAULTS: dict[str, int] = {
    "AUTO_PAUSE_CONSECUTIVE_ERRORS": 5,
    "AUTO_PAUSE_CONSECUTIVE_ORDER_FAILURES": 3,
    "AUTO_PAUSE_HEARTBEAT_MULTIPLIER": 5,
    "AUTO_PAUSE_HEARTBEAT_MIN_SECONDS": 300,
    "AUTO_PAUSE_WATCHDOG_INTERVAL_SECONDS": 30,
}


@router.get(
    "/risk",
    response_model=RiskOut,
    dependencies=[Depends(get_current_user)],
)
async def get_risk(db: AsyncSession = Depends(get_db)):
    cfg = await RuntimeConfigService(db).get_many(list(_RISK_KEYS_DEFAULTS.keys()))
    return RiskOut(
        consecutive_errors=int(
            cfg["AUTO_PAUSE_CONSECUTIVE_ERRORS"]
            or _RISK_KEYS_DEFAULTS["AUTO_PAUSE_CONSECUTIVE_ERRORS"]
        ),
        consecutive_order_failures=int(
            cfg["AUTO_PAUSE_CONSECUTIVE_ORDER_FAILURES"]
            or _RISK_KEYS_DEFAULTS["AUTO_PAUSE_CONSECUTIVE_ORDER_FAILURES"]
        ),
        heartbeat_multiplier=int(
            cfg["AUTO_PAUSE_HEARTBEAT_MULTIPLIER"]
            or _RISK_KEYS_DEFAULTS["AUTO_PAUSE_HEARTBEAT_MULTIPLIER"]
        ),
        heartbeat_min_seconds=int(
            cfg["AUTO_PAUSE_HEARTBEAT_MIN_SECONDS"]
            or _RISK_KEYS_DEFAULTS["AUTO_PAUSE_HEARTBEAT_MIN_SECONDS"]
        ),
        watchdog_interval_seconds=int(
            cfg["AUTO_PAUSE_WATCHDOG_INTERVAL_SECONDS"]
            or _RISK_KEYS_DEFAULTS["AUTO_PAUSE_WATCHDOG_INTERVAL_SECONDS"]
        ),
    )


@router.put(
    "/risk",
    response_model=RiskOut,
    dependencies=[Depends(get_current_user)],
)
async def put_risk(body: RiskIn, db: AsyncSession = Depends(get_db)):
    svc = RuntimeConfigService(db)
    mapping = {
        "AUTO_PAUSE_CONSECUTIVE_ERRORS": body.consecutive_errors,
        "AUTO_PAUSE_CONSECUTIVE_ORDER_FAILURES": body.consecutive_order_failures,
        "AUTO_PAUSE_HEARTBEAT_MULTIPLIER": body.heartbeat_multiplier,
        "AUTO_PAUSE_HEARTBEAT_MIN_SECONDS": body.heartbeat_min_seconds,
        "AUTO_PAUSE_WATCHDOG_INTERVAL_SECONDS": body.watchdog_interval_seconds,
    }
    for key, value in mapping.items():
        await svc.set(key, str(value), encrypt=False)
    return await get_risk(db=db)


# ── 测试发送 ──────────────────────────────────────────────────


@router.post(
    "/notifications/test",
    dependencies=[Depends(get_current_user)],
)
async def send_test_notification(body: TestIn, db: AsyncSession = Depends(get_db)):
    """触发一条测试通知，验证当前配置是否能送达。

    直接用注入的 db session 取配置 + 调用具体渠道方法，不走 NotificationService._send
    的全局 session 路径，便于在请求上下文里精确报错。
    """
    cfg = await RuntimeConfigService(db).get_many(
        [
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHAT_ID",
            "SMTP_HOST",
            "SMTP_PORT",
            "SMTP_USERNAME",
            "SMTP_PASSWORD",
            "SMTP_FROM",
            "SMTP_TO",
            "SMTP_USE_TLS",
        ]
    )
    svc = NotificationService()
    title = "测试通知"
    message = f"如果你收到这条，说明 {body.channel} 通道配置成功。"

    if body.channel == "telegram":
        if not (cfg.get("TELEGRAM_BOT_TOKEN") and cfg.get("TELEGRAM_CHAT_ID")):
            raise HTTPException(status_code=502, detail="Telegram 未配置")
        try:
            await svc._send_telegram(message, cfg["TELEGRAM_BOT_TOKEN"], cfg["TELEGRAM_CHAT_ID"])
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:  # email
        if not all(cfg.get(k) for k in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_TO")):
            raise HTTPException(status_code=502, detail="SMTP 未配置完整")
        try:
            await svc._send_email(cfg, title, message)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"ok": True}
