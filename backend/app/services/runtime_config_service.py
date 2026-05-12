"""RuntimeConfig 读写服务 + 启动 bootstrap。

承载前端可改的运行时配置（Telegram / SMTP / 风控阈值）。
- 敏感字段（ENCRYPTED_KEYS 列出的）以 Fernet 密文存储
- 其余字段明文存储
- 启动时把 .env 里的对应字段灌入 runtime_config 表，已存在的 key 不覆盖
"""

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.encryption import decrypt_secret, encrypt_secret
from app.models.runtime_config import RuntimeConfig

logger = logging.getLogger(__name__)

ENCRYPTED_KEYS: frozenset[str] = frozenset({"TELEGRAM_BOT_TOKEN", "SMTP_PASSWORD"})

# runtime_config key → Settings 字段名。bootstrap 时按此映射从 .env 拉默认值。
_ENV_MAPPING: dict[str, str] = {
    "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
    "TELEGRAM_CHAT_ID": "telegram_chat_id",
    "SMTP_HOST": "smtp_host",
    "SMTP_PORT": "smtp_port",
    "SMTP_USERNAME": "smtp_username",
    "SMTP_PASSWORD": "smtp_password",
    "SMTP_FROM": "smtp_from",
    "SMTP_TO": "smtp_to",
    "SMTP_USE_TLS": "smtp_use_tls",
    "AUTO_PAUSE_CONSECUTIVE_ERRORS": "auto_pause_consecutive_errors",
    "AUTO_PAUSE_CONSECUTIVE_ORDER_FAILURES": "auto_pause_consecutive_order_failures",
    "AUTO_PAUSE_HEARTBEAT_MULTIPLIER": "auto_pause_heartbeat_multiplier",
    "AUTO_PAUSE_HEARTBEAT_MIN_SECONDS": "auto_pause_heartbeat_min_seconds",
    "AUTO_PAUSE_WATCHDOG_INTERVAL_SECONDS": "auto_pause_watchdog_interval_seconds",
}


class RuntimeConfigService:
    """读写 runtime_config 表，自动处理敏感字段的加解密。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, key: str) -> str | None:
        row = (
            await self._session.execute(select(RuntimeConfig).where(RuntimeConfig.key == key))
        ).scalar_one_or_none()
        if row is None or row.value is None:
            return None
        if row.is_encrypted:
            try:
                return decrypt_secret(row.value)
            except Exception:
                logger.exception("解密 runtime_config 失败 key=%s", key)
                return None
        return row.value

    async def get_many(self, keys: list[str]) -> dict[str, str | None]:
        result: dict[str, str | None] = dict.fromkeys(keys)
        rows = (
            (await self._session.execute(select(RuntimeConfig).where(RuntimeConfig.key.in_(keys))))
            .scalars()
            .all()
        )
        for row in rows:
            if row.value is None:
                continue
            if row.is_encrypted:
                try:
                    result[row.key] = decrypt_secret(row.value)
                except Exception:
                    logger.exception("解密 runtime_config 失败 key=%s", row.key)
            else:
                result[row.key] = row.value
        return result

    async def set(self, key: str, value: str | None, *, encrypt: bool) -> None:
        if value is None:
            await self._session.execute(delete(RuntimeConfig).where(RuntimeConfig.key == key))
            await self._session.commit()
            return

        stored = encrypt_secret(value) if encrypt else value
        existing = (
            await self._session.execute(select(RuntimeConfig).where(RuntimeConfig.key == key))
        ).scalar_one_or_none()
        if existing is None:
            self._session.add(RuntimeConfig(key=key, value=stored, is_encrypted=encrypt))
        else:
            existing.value = stored
            existing.is_encrypted = encrypt
        await self._session.commit()


async def bootstrap_runtime_config_from_env(session: AsyncSession) -> None:
    """启动时把 .env 中的值灌入 runtime_config 表，已存在的 key 不覆盖。

    这样升级老部署不会丢失之前在 .env 里写的配置；
    新部署可以让用户登录后在前端覆盖。
    """
    settings = get_settings()
    svc = RuntimeConfigService(session)

    existing_keys = set((await session.execute(select(RuntimeConfig.key))).scalars().all())

    for config_key, settings_attr in _ENV_MAPPING.items():
        if config_key in existing_keys:
            continue
        raw = getattr(settings, settings_attr, None)
        if raw is None or raw == "":
            continue
        await svc.set(config_key, str(raw), encrypt=(config_key in ENCRYPTED_KEYS))
    logger.info("runtime_config bootstrap 完成")
