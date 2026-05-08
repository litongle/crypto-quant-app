"""
数据库连接管理 - 懒初始化 + 可重置

核心改动：
- engine / session_maker 不再模块级创建，改为首次使用时懒初始化
- reset_database() 支持安装向导切换配置后重连
- init_db() 用于首次建表
- get_session() 别名，修复代码库中 Depends(get_session) 引用
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

logger = logging.getLogger(__name__)

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
            eng,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    else:
        _test_engine = None
        _engine = None
        _session_maker = None


class Base(DeclarativeBase):
    """SQLAlchemy 基类"""

    pass


def _inspect_schema_state(sync_conn) -> dict[str, object]:
    """采集当前数据库结构状态，用于决定初始化/升级策略。"""
    inspector = inspect(sync_conn)
    table_names = set(inspector.get_table_names())
    strategy_columns: set[str] = set()
    if "strategy_instances" in table_names:
        strategy_columns = {col["name"] for col in inspector.get_columns("strategy_instances")}
    current_revision = None
    if "alembic_version" in table_names:
        current_revision = sync_conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()

    app_tables = {
        "users",
        "strategy_templates",
        "strategy_instances",
        "orders",
        "signals",
    }
    return {
        "table_names": table_names,
        "strategy_columns": strategy_columns,
        "has_app_tables": bool(table_names & app_tables),
        "has_alembic_version": "alembic_version" in table_names,
        "current_revision": current_revision,
    }


def _repair_strategy_instances_schema(sync_conn) -> bool:
    """修复历史部署中 strategy_instances 的缺失列。

    旧版本启动逻辑会对已有旧库直接 stamp 到 head，导致 Alembic 版本号前进，
    但实际列并没有补齐。这里做幂等修复，确保云端旧库能自愈。
    """
    inspector = inspect(sync_conn)
    table_names = set(inspector.get_table_names())
    if "strategy_instances" not in table_names:
        return False

    existing_columns = {col["name"] for col in inspector.get_columns("strategy_instances")}
    repaired = False
    dialect = sync_conn.dialect.name

    if "state_json" not in existing_columns:
        if dialect == "postgresql":
            sync_conn.execute(
                text("ALTER TABLE strategy_instances ADD COLUMN IF NOT EXISTS state_json JSON")
            )
        else:
            sync_conn.execute(text("ALTER TABLE strategy_instances ADD COLUMN state_json JSON"))
        repaired = True

    if "workspace_state" not in existing_columns:
        if dialect == "postgresql":
            sync_conn.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        CREATE TYPE instance_workspace_state AS ENUM ('draft', 'library', 'running');
                    EXCEPTION
                        WHEN duplicate_object THEN NULL;
                    END
                    $$;
                    """
                )
            )
            sync_conn.execute(
                text(
                    """
                    ALTER TABLE strategy_instances
                    ADD COLUMN IF NOT EXISTS workspace_state instance_workspace_state
                    """
                )
            )
            sync_conn.execute(
                text(
                    """
                    UPDATE strategy_instances
                    SET workspace_state = CASE
                        WHEN status = 'running' THEN 'running'::instance_workspace_state
                        ELSE 'library'::instance_workspace_state
                    END
                    WHERE workspace_state IS NULL
                    """
                )
            )
            sync_conn.execute(
                text(
                    """
                    ALTER TABLE strategy_instances
                    ALTER COLUMN workspace_state SET DEFAULT 'library'
                    """
                )
            )
            sync_conn.execute(
                text(
                    """
                    ALTER TABLE strategy_instances
                    ALTER COLUMN workspace_state SET NOT NULL
                    """
                )
            )
            sync_conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_strategy_instances_workspace_state
                    ON strategy_instances (workspace_state)
                    """
                )
            )
        else:
            sync_conn.execute(
                text(
                    """
                    ALTER TABLE strategy_instances
                    ADD COLUMN workspace_state VARCHAR(20) NOT NULL DEFAULT 'library'
                    """
                )
            )
            sync_conn.execute(
                text(
                    """
                    UPDATE strategy_instances
                    SET workspace_state = CASE
                        WHEN status = 'running' THEN 'running'
                        ELSE 'library'
                    END
                    """
                )
            )
            sync_conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_strategy_instances_workspace_state
                    ON strategy_instances (workspace_state)
                    """
                )
            )
        repaired = True

    if "source_instance_id" not in existing_columns:
        if dialect == "postgresql":
            sync_conn.execute(
                text(
                    """
                    ALTER TABLE strategy_instances
                    ADD COLUMN IF NOT EXISTS source_instance_id INTEGER
                    """
                )
            )
            sync_conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_strategy_instances_source_instance_id
                    ON strategy_instances (source_instance_id)
                    """
                )
            )
            sync_conn.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'fk_strategy_instances_source_instance_id_strategy_instances'
                        ) THEN
                            ALTER TABLE strategy_instances
                            ADD CONSTRAINT fk_strategy_instances_source_instance_id_strategy_instances
                            FOREIGN KEY (source_instance_id)
                            REFERENCES strategy_instances (id)
                            ON DELETE SET NULL;
                        END IF;
                    END
                    $$;
                    """
                )
            )
        else:
            sync_conn.execute(
                text("ALTER TABLE strategy_instances ADD COLUMN source_instance_id INTEGER")
            )
            sync_conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_strategy_instances_source_instance_id
                    ON strategy_instances (source_instance_id)
                    """
                )
            )
        repaired = True

    if "last_started_at" not in existing_columns:
        if dialect == "postgresql":
            sync_conn.execute(
                text(
                    """
                    ALTER TABLE strategy_instances
                    ADD COLUMN IF NOT EXISTS last_started_at TIMESTAMP WITH TIME ZONE
                    """
                )
            )
        else:
            sync_conn.execute(
                text("ALTER TABLE strategy_instances ADD COLUMN last_started_at DATETIME")
            )
        repaired = True

    if "last_stopped_at" not in existing_columns:
        if dialect == "postgresql":
            sync_conn.execute(
                text(
                    """
                    ALTER TABLE strategy_instances
                    ADD COLUMN IF NOT EXISTS last_stopped_at TIMESTAMP WITH TIME ZONE
                    """
                )
            )
        else:
            sync_conn.execute(
                text("ALTER TABLE strategy_instances ADD COLUMN last_stopped_at DATETIME")
            )
        repaired = True

    return repaired


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
    """Initialize database tables (called on first setup).

    Uses Alembic migrations when the database is already under Alembic control.
    For fresh databases, create_all() + stamp head is enough.
    For legacy drifted databases, perform targeted schema repair.
    """
    # Ensure data directory exists (SQLite)
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.split("///")[-1]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # Import all models so Base.metadata knows all tables
    import app.models  # noqa: F401

    engine = await get_engine()
    schema_state: dict[str, object] = {}
    async with engine.begin() as conn:
        schema_state = await conn.run_sync(_inspect_schema_state)
        needs_create_all = not schema_state.get("has_app_tables") or not schema_state.get(
            "has_alembic_version"
        )
        if needs_create_all:
            await conn.run_sync(Base.metadata.create_all)

    # Fresh DB: create_all + stamp head.
    # Existing DB with alembic_version: upgrade head.
    # Existing DB without alembic_version: avoid replaying migrations over a
    # partially managed schema; rely on create_all + targeted repair instead.
    try:
        from alembic.config import Config as AlembicConfig

        from alembic import command

        alembic_cfg = AlembicConfig()
        alembic_cfg.set_main_option("script_location", "alembic")
        alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
        if not schema_state.get("has_app_tables"):
            await asyncio.to_thread(command.stamp, alembic_cfg, "head")
            logger.info("Alembic version stamped to head")
        elif schema_state.get("has_alembic_version"):
            await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
            logger.info("Alembic migrations upgraded to head")
        else:
            logger.warning(
                "Detected existing app tables without alembic_version; "
                "skipping Alembic replay and applying targeted schema repair"
            )
    except Exception:
        if schema_state.get("has_alembic_version"):
            logger.exception("Alembic upgrade failed for existing managed database")
            raise
        logger.warning("Alembic initialization unavailable for fresh database; continuing")

    async with engine.begin() as conn:
        repaired = await conn.run_sync(_repair_strategy_instances_schema)
        if repaired:
            logger.warning("Repaired legacy strategy_instances schema drift during startup")


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
