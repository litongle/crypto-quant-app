"""
安装向导 API - 首次运行初始化

两个接口：
- GET /status：检查是否需要安装
- POST /complete：完成安装（写入 .env + 建表 + 创建管理员）

服务端执行顺序：
1. 生成安全密钥 + 写入 .env
2. reload_settings() 热切换配置
3. reset_database() 丢弃旧引擎
4. init_db() 按新配置建表
5. 创建管理员
6. SETUP_COMPLETE=true 写回 .env
7. 再次 reload + reset 让进程用最终配置
"""
import secrets
import logging
import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field

from app.config import get_settings, reload_settings
from app.database import init_db, reset_database, get_db_context
from app.models.user import User
from app.core.security import hash_password

router = APIRouter()
logger = logging.getLogger(__name__)

# P0-5: 增加进程级锁，防止安装向导竞态条件
_setup_lock = asyncio.Lock()


class SetupRequest(BaseModel):
    """安装请求"""
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, description="管理员密码，至少8位")
    admin_name: str = Field(min_length=2, max_length=100, description="管理员名称")

    database_url: str = "sqlite+aiosqlite:///./data/crypto_quant.db"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://127.0.0.1:8000", "http://localhost:8000"]
    debug: bool = False


def write_env_file(values: dict[str, str]) -> None:
    """写入 .env 文件"""
    settings = get_settings()
    env_path: Path = settings.env_path
    env_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    for k, v in values.items():
        # 值含空格或特殊字符时加引号
        if " " in str(v) or any(c in str(v) for c in ("{", "}", "[", "]")):
            lines.append(f'{k}="{v}"')
        else:
            lines.append(f"{k}={v}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@router.get("/status")
async def setup_status():
    """检查是否需要安装"""
    settings = get_settings()
    return {
        "setup_required": settings.setup_required,
        "has_env_file": settings.env_path.exists(),
    }


@router.get("/env-defaults")
async def setup_env_defaults():
    """返回当前环境变量中预置的数据库/Redis配置，供安装向导自动预填"""
    import re
    settings = get_settings()
    db_url = settings.database_url or ""
    redis_url = settings.redis_url or "redis://localhost:6379/0"

    # 解析 DATABASE_URL，提取各字段
    db_type = "sqlite"
    pg_host = "localhost"
    pg_port = "5432"
    pg_user = "postgres"
    pg_password = ""
    pg_dbname = "crypto_quant"

    if db_url.startswith("postgresql"):
        db_type = "postgresql"
        # postgresql+asyncpg://user:password@host:port/dbname
        m = re.match(
            r"postgresql(?:\+\w+)?://([^:@]*)(?::([^@]*))?@([^:/]+)(?::(\d+))?/(\S+)",
            db_url,
        )
        if m:
            pg_user = m.group(1) or "postgres"
            pg_password = m.group(2) or ""
            pg_host = m.group(3) or "localhost"
            pg_port = m.group(4) or "5432"
            pg_dbname = m.group(5) or "crypto_quant"

    return {
        "db_type": db_type,
        "pg_host": pg_host,
        "pg_port": pg_port,
        "pg_user": pg_user,
        "pg_password": pg_password,
        "pg_dbname": pg_dbname,
        "redis_url": redis_url,
    }


@router.post("/complete")
async def complete_setup(req: SetupRequest):
    """完成安装"""
    async with _setup_lock:
        settings = get_settings()

        # 防止重复安装
        if settings.env_path.exists() and not settings.setup_required:
            raise HTTPException(status_code=409, detail="应用已初始化，不能重复安装")

    # Step 1: 生成配置并写入 .env（SETUP_COMPLETE=false，先不标记完成）
    env_values = {
        "APP_NAME": "CryptoQuant",
        "APP_VERSION": "1.0.0",
        "DEBUG": str(req.debug).lower(),
        "ENVIRONMENT": "production" if not req.debug else "development",
        "SECRET_KEY": secrets.token_urlsafe(48),
        "JWT_SECRET_KEY": secrets.token_urlsafe(48),
        "DATABASE_URL": req.database_url,
        "REDIS_URL": req.redis_url,
        "JWT_ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "REFRESH_TOKEN_EXPIRE_DAYS": "7",
        "CORS_ORIGINS": ",".join(req.cors_origins),
        "SETUP_COMPLETE": "false",
    }

    write_env_file(env_values)

    # Step 2-3: 热切换配置 + 丢弃旧引擎
    reload_settings()
    await reset_database()

    # Step 4: 按新配置建表
    try:
        await init_db()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"数据库初始化失败：{str(e)}。请检查 DATABASE_URL 是否正确。",
        )

    # Step 5: 创建管理员
    try:
        async with get_db_context() as session:
            admin = User(
                email=req.admin_email,
                hashed_password=hash_password(req.admin_password),
                name=req.admin_name,
                status="active",
                risk_level="moderate",
                is_superuser=True,
            )
            session.add(admin)
            await session.flush()
            await session.commit()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"管理员创建失败：{str(e)}",
        )

    # Step 6: 标记安装完成
    env_values["SETUP_COMPLETE"] = "true"
    write_env_file(env_values)

    # Step 7: 再次热切换配置（不再 reset_database，否则会清掉刚建好的表和数据）
    reload_settings()

    return {
        "success": True,
        "redirect": "/web/",
        "message": "安装完成，请登录",
    }
