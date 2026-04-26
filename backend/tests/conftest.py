"""
测试配置 — 共享 fixtures

使用 SQLite 内存数据库 + 测试专用 settings，不依赖外部服务。
"""
import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.database import Base, get_db, get_session
from app.config import Settings, get_settings


# ==================== 测试专用配置 ====================

class TestSettings(Settings):
    """测试配置 — 覆盖所有默认值，避免依赖 .env"""
    debug: bool = True  # 测试环境需要 debug
    environment: str = "test"
    secret_key: str = "test-secret-key-for-testing-only-min-32-chars"
    jwt_secret_key: str = "test-jwt-secret-key-for-testing-only-min-32"
    database_url: str = "sqlite+aiosqlite:///./test_data/test.db"
    redis_url: str = "redis://localhost:6379/15"
    cors_origins: str = "http://localhost:8000"


@pytest.fixture(scope="session")
def test_settings():
    """测试专用配置实例"""
    return TestSettings()


@pytest.fixture(scope="session", autouse=True)
def override_settings(test_settings):
    """覆盖 get_settings 缓存"""
    get_settings.cache_clear()
    # 注入测试配置到缓存
    get_settings._cache = test_settings
    yield test_settings
    get_settings.cache_clear()


# ==================== 数据库 Fixtures ====================

@pytest_asyncio.fixture(scope="session")
async def engine():
    """创建测试数据库引擎"""
    from sqlalchemy.ext.asyncio import create_async_engine
    import os
    os.makedirs("./test_data", exist_ok=True)

    eng = create_async_engine(
        "sqlite+aiosqlite:///./test_data/test.db",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # 创建所有表
    async with eng.begin() as conn:
        import app.models  # noqa: F401 — 确保所有模型注册
        await conn.run_sync(Base.metadata.create_all)

    yield eng

    # 清理
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await eng.dispose()

    # 删除测试数据库文件
    try:
        os.remove("./test_data/test.db")
    except Exception:
        pass


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator:
    """每个测试独立的数据库会话"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """HTTP 测试客户端"""
    from app.main import create_app

    app = create_app()

    # 覆盖 get_db 和 get_session 依赖（auth 路由用 get_session）
    async def override_get_db():
        yield db_session

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session] = override_get_session

    # 使用测试 SQLite engine 替换 app 内部 engine，避免连 PostgreSQL
    from app.database import _set_test_engine
    _set_test_engine(db_session.get_bind())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    _set_test_engine(None)


# ==================== 用户 Fixtures ====================

@pytest_asyncio.fixture
async def test_user(db_session):
    """创建测试用户（幂等：已存在则返回）"""
    from app.models.user import User
    from app.core.security import hash_password
    from sqlalchemy import select

    # 先查是否已存在（register 测试可能已创建）
    result = await db_session.execute(
        select(User).where(User.email == "test@example.com")
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    user = User(
        name="testuser",
        email="test@example.com",
        hashed_password=hash_password("testpass123"),
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_token(test_user):
    """为测试用户生成 JWT token"""
    from app.core.security import create_access_token
    return create_access_token({"sub": str(test_user.id)})


@pytest_asyncio.fixture
async def auth_headers(auth_token):
    """带认证的请求头"""
    return {"Authorization": f"Bearer {auth_token}"}
