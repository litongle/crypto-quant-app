"""
Redis 连接管理

改动：不再模块级缓存 settings，改为函数内取
"""
import asyncio
from typing import AsyncGenerator

import redis.asyncio as redis
from redis.asyncio import ConnectionPool, Redis

from app.config import get_settings

# 连接池
_pool: ConnectionPool | None = None
# 全局客户端单例
_redis_client: Redis | None = None
# PRF-02: 加锁保护全局连接池初始化
_pool_lock = asyncio.Lock()


async def get_redis_pool() -> ConnectionPool:
    """获取 Redis 连接池（线程安全）"""
    global _pool
    if _pool is None:
        async with _pool_lock:
            # 双重检查：获取锁后再检查一次
            if _pool is None:
                settings = get_settings()
                _pool = ConnectionPool.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    max_connections=20,
                )
    return _pool


async def get_redis_client() -> Redis:
    """获取全局 Redis 客户端单例（复用连接池）

    P0 修复: 不能在持有 _pool_lock 时再调 get_redis_pool 否则死锁
    (asyncio.Lock 不可重入)。先在锁外拿到 pool,再进锁创建 client。
    """
    global _redis_client
    if _redis_client is None:
        # 锁外先拿 pool(它内部会用 _pool_lock 自己保护)
        pool = await get_redis_pool()
        async with _pool_lock:
            if _redis_client is None:
                _redis_client = Redis(connection_pool=pool)
    return _redis_client


async def get_redis() -> AsyncGenerator[Redis, None]:
    """获取 Redis 客户端的依赖"""
    client = await get_redis_client()
    yield client
    # 注意：全局单例不在这里关闭，由 close_redis 统一关闭


async def close_redis() -> None:
    """关闭 Redis 连接池和客户端"""
    global _pool, _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
    if _pool is not None:
        await _pool.disconnect()
        _pool = None


async def reset_redis() -> None:
    """重置 Redis 连接池（安装向导切换配置后调用）"""
    await close_redis()
