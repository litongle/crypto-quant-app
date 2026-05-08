"""
应用配置管理 - 支持无 .env 启动 + 运行时重载 + 生产安全校验
"""

import sys
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# 默认开发密钥（仅用于 development 环境）
_DEFAULT_SECRET_KEY = "dev-secret-key-change-me"
_DEFAULT_JWT_SECRET_KEY = "dev-jwt-secret-key-change-me"


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用信息
    app_name: str = "CryptoQuant"
    app_version: str = "1.0.0"
    debug: bool = False  # P0-2: 默认关闭，开发环境需显式开启

    # 环境 & 安装状态
    environment: str = "development"
    setup_complete: bool = False
    allow_insecure_default_secrets: bool = False

    # 安全密钥（开发占位值，生产环境必须通过 .env 或安装向导设置）
    secret_key: str = _DEFAULT_SECRET_KEY
    jwt_secret_key: str = _DEFAULT_JWT_SECRET_KEY

    # 数据库（默认 SQLite，安装向导可切换 PostgreSQL）
    database_url: str = "sqlite+aiosqlite:///./data/crypto_quant.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # CORS
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:8000,http://localhost:8000"

    # 通知服务 — P0-1
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    # 自停 / 异常告警 (auto-pause v1)
    auto_pause_consecutive_errors: int = 5
    auto_pause_consecutive_order_failures: int = 3
    auto_pause_heartbeat_multiplier: int = 5
    auto_pause_heartbeat_min_seconds: int = 300
    auto_pause_watchdog_interval_seconds: int = 30
    wecom_webhook_url: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        if isinstance(self.cors_origins, str):
            return [x.strip() for x in self.cors_origins.split(",") if x.strip()]
        return self.cors_origins

    @property
    def env_path(self) -> Path:
        return ENV_PATH

    @property
    def setup_required(self) -> bool:
        # Cloud platforms like Render inject settings as environment variables
        # without creating a local .env file, so installation state must depend
        # on the explicit setup flag rather than file presence.
        return not self.setup_complete

    @property
    def is_production(self) -> bool:
        """是否为生产环境"""
        return self.environment.lower() in ("production", "prod", "staging")

    def validate_production_secrets(self) -> None:
        """安全校验 — 默认密钥仅允许显式 opt-in 的非生产场景使用。"""
        if self.environment.lower() == "test":
            return
        errors = []
        if not self.allow_insecure_default_secrets and self.secret_key == _DEFAULT_SECRET_KEY:
            errors.append("secret_key 仍为默认开发值，必须通过 .env 或安装向导设置")
        if (
            not self.allow_insecure_default_secrets
            and self.jwt_secret_key == _DEFAULT_JWT_SECRET_KEY
        ):
            errors.append("jwt_secret_key 仍为默认开发值，必须通过 .env 或安装向导设置")
        if self.is_production and self.debug:
            errors.append("生产环境不允许 debug=True，请设置 DEBUG=false")

        if errors:
            print("\n" + "=" * 60, file=sys.stderr)
            print("🚨 生产环境安全校验失败，拒绝启动！", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            for i, err in enumerate(errors, 1):
                print(f"  {i}. {err}", file=sys.stderr)
            print("\n请在 .env 文件中设置正确的密钥后重试。", file=sys.stderr)
            print("=" * 60 + "\n", file=sys.stderr)
            sys.exit(1)


@lru_cache
def get_settings() -> Settings:
    """获取配置单例（含生产安全校验）"""
    cached = getattr(get_settings, "_cache", None)
    if cached is not None:
        return cached
    settings = Settings()
    settings.validate_production_secrets()
    return settings


def reload_settings() -> Settings:
    """重载配置（安装向导写入 .env 后调用）"""
    if hasattr(get_settings, "_cache"):
        delattr(get_settings, "_cache")
    get_settings.cache_clear()
    return get_settings()
