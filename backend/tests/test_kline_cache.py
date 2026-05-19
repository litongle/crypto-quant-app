"""K 线缓存 repository 测试

覆盖核心契约：
1. bulk_upsert 空表插入
2. bulk_upsert 重复行被唯一约束跳过（PG: ON CONFLICT / SQLite: ON CONFLICT，都用 INSERT OR IGNORE 语义）
3. get_range 按 ts 升序返回
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.kline_cache import KlineCache
from app.repositories import kline_cache_repo

pytestmark = pytest.mark.asyncio


def _make_row(ts: int, *, exchange: str = "binance", symbol: str = "BTCUSDT", interval: str = "1h"):
    return {
        "exchange": exchange,
        "symbol": symbol,
        "interval": interval,
        "ts": ts,
        "open": Decimal("100.0"),
        "high": Decimal("110.0"),
        "low": Decimal("90.0"),
        "close": Decimal("105.0"),
        "volume": Decimal("1000.0"),
    }


async def test_bulk_upsert_inserts_new_rows(db_session):
    """空表 upsert 10 行 → 表里有 10 行"""
    rows = [_make_row(1_700_000_000_000 + i * 3_600_000) for i in range(10)]

    inserted = await kline_cache_repo.bulk_upsert(db_session, rows)
    await db_session.commit()

    assert inserted == 10
    result = await db_session.execute(select(KlineCache))
    assert len(result.scalars().all()) == 10


async def test_bulk_upsert_ignores_duplicates(db_session):
    """同样 10 行 upsert 两次 → 表里仍 10 行，第二次不报错"""
    rows = [_make_row(1_700_000_000_000 + i * 3_600_000) for i in range(10)]

    await kline_cache_repo.bulk_upsert(db_session, rows)
    await db_session.commit()

    # 第二次相同内容
    inserted_again = await kline_cache_repo.bulk_upsert(db_session, rows)
    await db_session.commit()

    # SQLite/PG 在 ON CONFLICT DO NOTHING 下，重复行 rowcount=0
    assert inserted_again == 0
    result = await db_session.execute(select(KlineCache))
    assert len(result.scalars().all()) == 10


async def test_get_range_returns_in_order(db_session):
    """插 5 根不同 ts（乱序），get_range 按 ts 升序返回"""
    base = 1_700_000_000_000
    interval_ms = 3_600_000
    # 乱序插入
    ts_list = [
        base + 3 * interval_ms,
        base,
        base + 4 * interval_ms,
        base + 1 * interval_ms,
        base + 2 * interval_ms,
    ]
    rows = [_make_row(ts) for ts in ts_list]

    await kline_cache_repo.bulk_upsert(db_session, rows)
    await db_session.commit()

    fetched = await kline_cache_repo.get_range(
        db_session,
        exchange="binance",
        symbol="BTCUSDT",
        interval="1h",
        start_ms=base,
        end_ms=base + 10 * interval_ms,
    )

    assert len(fetched) == 5
    fetched_ts = [r.ts for r in fetched]
    assert fetched_ts == sorted(ts_list)


async def test_get_range_filters_by_exchange_symbol_interval(db_session):
    """get_range 必须用 (exchange, symbol, interval) 过滤，跨 symbol 不会串"""
    base = 1_700_000_000_000
    rows = [
        _make_row(base, symbol="BTCUSDT"),
        _make_row(base, symbol="ETHUSDT"),
        _make_row(base, symbol="BTCUSDT", interval="4h"),
    ]
    await kline_cache_repo.bulk_upsert(db_session, rows)
    await db_session.commit()

    fetched = await kline_cache_repo.get_range(
        db_session, "binance", "BTCUSDT", "1h", base - 1000, base + 1000
    )
    assert len(fetched) == 1
    assert fetched[0].symbol == "BTCUSDT"
    assert fetched[0].interval == "1h"
