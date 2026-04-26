"""
数据库连接管理 - 懒初始化 + 可重置

核心改动：
- engine / session_maker 不再模块级创建，改为首次使用时懒初始化
- reset_database() 支持安装向导切换配置后重连
- init_db() 用于首次建表
- get_session() 别名，修复代码库中 Depends(get_session) 引用
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

_engine = None
_session_maker = None
_lock = asyncio.Lock()
_test_engine = None  # 测试注入用


def _set_test_engine(eng):
    """注入测试 engine（测试专用，生产不调用）"""
    global _test_engine, _engine, _session_maker
    if eng is not None:
        _test_engine = eng
        _engine = eng
        _session_maker = async_sessionmaker(
            eng, class_=AsyncSession, expire_on_commit=False,
            autocommit=False, autoflush=False,
        )
    else:
        _test_engine = None
        _engine = None
        _session_maker = None


class Base(DeclarativeBase):
    """SQLAlchemy 基类"""
    pass


def _build_engine():
    """根据当前配置创建数据库引擎"""
    settings = get_settings()
    kwargs = {
        "echo": settings.debug,
        "pool_pre_ping": True,
    }
    # SQLite 和 PostgreSQL 参数不同
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20

    return create_async_engine(settings.database_url, **kwargs)


async def get_engine():
    """获取数据库引擎（懒初始化）"""
    global _engine
    if _engine is None:
        async with _lock:
            if _engine is None:
                _engine = _build_engine()
    return _engine


async def get_session_maker():
    """获取会话工厂（懒初始化）"""
    global _session_maker
    if _session_maker is None:
        engine = await get_engine()
        _session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_maker


async def reset_database():
    """重置数据库连接（安装向导切换配置后调用）"""
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_maker = None


async def init_db():
    """初始化数据库表（首次安装时调用）"""
    # 确保数据目录存在（SQLite 需要）
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.split("///")[-1]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # 导入所有模型，确保 Base.metadata 知道所有表
    import app.models  # noqa: F401

    engine = await get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话的依赖

    P1-6: 不再自动 commit，由路由层显式控制事务。
    路由通过 Depends(get_db) 获取 session，自己决定何时 commit。
    如果路由没有显式 commit，退出时自动 rollback（安全默认）。
    """
    session_maker = await get_session_maker()
    async with session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（get_db 的别名，修复代码库中 Depends(get_session) 引用）"""
    async for session in get_db():
        yield session


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话的上下文管理器（用于非依赖注入场景）

    P1-6: 不自动 commit，调用方自行控制。安全起见退出时 rollback。
    """
    session_maker = await get_session_maker()
    async with session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
