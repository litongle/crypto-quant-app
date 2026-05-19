"""K 线缓存仓储 — 支持范围查询和 dialect-aware 批量 upsert（去重）

为什么不用 BaseRepository：
- 批量 upsert 需要 dialect 特化（PG: ON CONFLICT DO NOTHING / SQLite: INSERT OR IGNORE）
- BaseRepository 的单条 create/update 在万级行写入下太慢
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kline_cache import KlineCache

logger = logging.getLogger(__name__)


async def get_range(
    session: AsyncSession,
    exchange: str,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
) -> list[KlineCache]:
    """按 ts 升序返回 [start_ms, end_ms] 范围内的缓存 K 线（含端点）。"""
    stmt = (
        select(KlineCache)
        .where(
            KlineCache.exchange == exchange,
            KlineCache.symbol == symbol,
            KlineCache.interval == interval,
            KlineCache.ts >= start_ms,
            KlineCache.ts <= end_ms,
        )
        .order_by(KlineCache.ts.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def bulk_upsert(session: AsyncSession, rows: Iterable[dict[str, Any]]) -> int:
    """批量插入，遇到唯一约束冲突自动跳过。返回实际插入行数。

    rows 元素至少包含 exchange / symbol / interval / ts / open / high / low / close / volume。
    PG 走 ON CONFLICT DO NOTHING，SQLite 走 INSERT OR IGNORE。

    分 batch — PG 协议 32767 参数上限,本表 10 字段 × N 行,一次塞 4 万行直接报
    InterfaceError 让缓存写失败,1m 30 天 43200 根会全军覆没。每 batch 1000 行
    留足余量。
    """
    payload = list(rows)
    if not payload:
        return 0

    batch_size = 1000

    dialect_name = session.bind.dialect.name if session.bind else ""
    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        def make_stmt(batch: list[dict[str, Any]]):
            s = pg_insert(KlineCache).values(batch)
            return s.on_conflict_do_nothing(index_elements=["exchange", "symbol", "interval", "ts"])

    elif dialect_name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        def make_stmt(batch: list[dict[str, Any]]):
            s = sqlite_insert(KlineCache).values(batch)
            return s.on_conflict_do_nothing(index_elements=["exchange", "symbol", "interval", "ts"])

    else:
        # 兜底（mysql 等）：逐条尝试插入，靠唯一约束去重。生产只跑 PG/SQLite，这里只保兼容。
        inserted = 0
        for row in payload:
            try:
                obj = KlineCache(**row)
                session.add(obj)
                await session.flush()
                inserted += 1
            except Exception:
                await session.rollback()
        return inserted

    total_inserted = 0
    for i in range(0, len(payload), batch_size):
        batch = payload[i : i + batch_size]
        result = await session.execute(make_stmt(batch))
        total_inserted += result.rowcount or 0
    await session.flush()
    return total_inserted
