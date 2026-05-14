"""权益曲线 (AssetService.get_equity_curve) 测试

覆盖：
1. snapshot 命中：曲线点 equity 从 daily_equity_snapshot 表取
2. snapshot 缺失 fallback：今天总权益 - 累计 PnL 反推早期日
3. PnL 时序：5 天前订单 PnL=1000 反推时该日及之前是低基线、之后是高基线
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.security import hash_password
from app.models.equity_snapshot import DailyEquitySnapshot
from app.models.exchange import ExchangeAccount
from app.models.order import Order
from app.models.user import User
from app.services.asset_service import AssetService


async def _make_user(session, email="equity@test.local"):
    u = User(
        email=email,
        name="equity_tester",
        hashed_password=hash_password("password123"),
        status="active",
    )
    session.add(u)
    await session.flush()
    await session.refresh(u)
    return u


async def _make_account(session, user_id, *, balance=Decimal("10000")):
    a = ExchangeAccount(
        user_id=user_id,
        exchange="binance",
        account_name="测试账户",
        is_active=True,
        status="active",
        balance=balance,
        frozen_balance=Decimal("0"),
    )
    a.set_api_key("FAKE_API_KEY_FOR_TEST_AAAAA")
    a.set_secret_key("FAKE_SECRET_KEY_FOR_TEST_BBBBB")
    session.add(a)
    await session.flush()
    await session.refresh(a)
    return a


@pytest.mark.asyncio
async def test_equity_curve_uses_snapshot_when_present(db_session):
    """snapshot 表有数据时，曲线点直接读 snapshot.total_equity"""
    user = await _make_user(db_session)
    account = await _make_account(db_session, user.id)

    today = datetime.now(UTC).date()
    # 写入今天 + 5 天前的快照
    db_session.add_all(
        [
            DailyEquitySnapshot(
                account_id=account.id,
                snapshot_date=today - timedelta(days=5),
                balance=Decimal("9500"),
                frozen_balance=Decimal("0"),
                positions_value=Decimal("0"),
                total_equity=Decimal("9500"),
            ),
            DailyEquitySnapshot(
                account_id=account.id,
                snapshot_date=today,
                balance=Decimal("10500"),
                frozen_balance=Decimal("0"),
                positions_value=Decimal("0"),
                total_equity=Decimal("10500"),
            ),
        ]
    )
    await db_session.commit()

    service = AssetService(db_session)
    data = await service.get_equity_curve(user_id=user.id, days=30)

    points = data["points"]
    by_date = {p["date"]: p["equity"] for p in points}
    five_days_ago = (today - timedelta(days=5)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    assert by_date[five_days_ago] == 9500.0
    assert by_date[today_str] == 10500.0


@pytest.mark.asyncio
async def test_equity_curve_fallback_when_no_snapshot(db_session):
    """snapshot 表无数据时，所有点用当前账户合计权益反推

    无订单情况下，反推结果应是 today_total_equity 平铺到所有 30 天。
    """
    user = await _make_user(db_session)
    await _make_account(db_session, user.id, balance=Decimal("12345.67"))
    await db_session.commit()

    service = AssetService(db_session)
    data = await service.get_equity_curve(user_id=user.id, days=30)

    points = data["points"]
    assert len(points) == 31  # range(days, -1, -1) 包含两端
    # 无订单时所有日反推结果一致
    equities = {round(p["equity"], 2) for p in points}
    assert equities == {12345.67}


@pytest.mark.asyncio
async def test_equity_curve_fallback_subtracts_pnl(db_session):
    """fallback 反推时，PnL 时序应在曲线上体现

    today balance=11000, 5 天前一笔 filled order pnl=1000；
    则 5 天前及更早的点 = 11000 - 1000 = 10000；4 天前及之后 = 11000。
    """
    user = await _make_user(db_session)
    account = await _make_account(db_session, user.id, balance=Decimal("11000"))

    five_days_ago = datetime.now(UTC) - timedelta(days=5)
    order = Order(
        account_id=account.id,
        symbol="BTCUSDT",
        side="buy",
        order_type="market",
        quantity=Decimal("0.01"),
        filled_quantity=Decimal("0.01"),
        price=Decimal("50000"),
        avg_fill_price=Decimal("60000"),
        order_value=Decimal("600"),
        status="filled",
        pnl=Decimal("1000"),
        created_at=five_days_ago,
        filled_at=five_days_ago,
    )
    db_session.add(order)
    await db_session.commit()

    service = AssetService(db_session)
    data = await service.get_equity_curve(user_id=user.id, days=30)

    by_date = {p["date"]: p["equity"] for p in data["points"]}
    today = datetime.now(UTC).date()
    six_days_ago_str = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    five_days_ago_str = (today - timedelta(days=5)).strftime("%Y-%m-%d")
    four_days_ago_str = (today - timedelta(days=4)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    # 5 天前订单当天的点 = 11000 - 1000 = 10000（订单 PnL 累加在 d+1..today，反推减掉）
    # 注意反推公式：equity[d] = today_total - sum(pnl filled_at in (d, today])
    # filled_at = d (5 天前)，所以 (d, today] 不含 d 自身 → pnl 全在窗口外
    # 6 天前的点 (d-1)：(d-1, today] 包含 5 天前的 pnl → 11000 - 1000 = 10000
    assert by_date[six_days_ago_str] == 10000.0
    # 5 天前点：fwd_pnl 不含当天 → 11000.0
    assert by_date[five_days_ago_str] == 11000.0
    assert by_date[four_days_ago_str] == 11000.0
    assert by_date[today_str] == 11000.0


@pytest.mark.asyncio
async def test_equity_curve_no_more_hardcoded_100000(db_session):
    """回归：账户余额 != 100000 时曲线起点不应再是硬编码 100000"""
    user = await _make_user(db_session)
    await _make_account(db_session, user.id, balance=Decimal("500"))
    await db_session.commit()

    service = AssetService(db_session)
    data = await service.get_equity_curve(user_id=user.id, days=30)

    # 没有任何点应该等于硬编码的 100000.0
    assert all(p["equity"] != 100000.0 for p in data["points"])
    # 而应该等于当前余额 500
    assert data["points"][-1]["equity"] == 500.0
