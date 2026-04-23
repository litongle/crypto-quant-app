"""
应用配置管理 - 支持无 .env 启动 + 运行时重载
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"


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
    debug: bool = True

    # 环境 & 安装状态
    environment: str = "development"
    setup_complete: bool = False

    # 安全密钥（开发占位值，安装向导生成真实密钥）
    secret_key: str = "dev-secret-key-change-me"
    jwt_secret_key: str = "dev-jwt-secret-key-change-me"

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
        return (not self.env_path.exists()) or (not self.setup_complete)


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


def reload_settings() -> Settings:
    """重载配置（安装向导写入 .env 后调用）"""
    get_settings.cache_clear()
    return get_settings()
