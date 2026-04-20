"""
Redis 连接管理
"""
import asyncio
from typing import AsyncGenerator

import redis.asyncio as redis
from redis.asyncio import ConnectionPool, Redis

from app.config import get_settings

settings = get_settings()

# 连接池
_pool: ConnectionPool | None = None
# PRF-02: 加锁保护全局连接池初始化
_pool_lock = asyncio.Lock()


async def get_redis_pool() -> ConnectionPool:
    """获取 Redis 连接池（线程安全）"""
    global _pool
    if _pool is None:
        async with _pool_lock:
            # 双重检查：获取锁后再检查一次
            if _pool is None:
                _pool = ConnectionPool.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    max_connections=20,
                )
    return _pool


async def get_redis() -> AsyncGenerator[Redis, None]:
    """获取 Redis 客户端的依赖"""
    pool = await get_redis_pool()
    client = Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.aclose()


async def close_redis() -> None:
    """关闭 Redis 连接池"""
    global _pool
    if _pool is not None:
        await _pool.disconnect()
        _pool = None
