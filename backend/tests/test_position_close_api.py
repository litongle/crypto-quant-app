"""持仓平仓 API 与持仓字段返回测试

覆盖：
1. AssetService.get_positions 返回字段（source / strategyInstanceId / strategyName / positionId / accountId / accountName）
2. POST /api/v1/trading/positions/{id}/close
   - 外部仓位（strategy_instance_id 为空）平仓成功
   - 策略仓位平仓后自动暂停 instance
   - 已关闭仓位返回 400
   - 跨用户访问返回 403
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from app.core.exchanges.base import OrderResult
from app.core.security import hash_password
from app.models.exchange import ExchangeAccount, Position
from app.models.order import Order
from app.models.strategy import StrategyInstance, StrategyTemplate
from app.models.user import User
from app.services.asset_service import AssetService
from app.services.order_service import OrderService

# ==================== Helpers ====================


async def _make_user(session, *, email: str) -> User:
    user = User(
        email=email,
        name="closetester",
        hashed_password=hash_password("password123"),
        status="active",
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def _make_account(session, user_id: int, *, exchange: str = "binance") -> ExchangeAccount:
    account = ExchangeAccount(
        user_id=user_id,
        exchange=exchange,
        account_name="共用账户",
        is_active=True,
        status="active",
        balance=Decimal("1000"),
        frozen_balance=Decimal("0"),
    )
    account.set_api_key("FAKE_API_KEY_FOR_TEST_AAAAA")
    account.set_secret_key("FAKE_SECRET_KEY_FOR_TEST_BBBBB")
    session.add(account)
    await session.flush()
    await session.refresh(account)
    return account


async def _make_template(session) -> StrategyTemplate:
    tpl = StrategyTemplate(
        code="rsi_test",
        name="RSI 测试",
        description="t",
        strategy_type="rsi_layered",
        params_schema={},
        risk_level="medium",
        is_active=True,
    )
    session.add(tpl)
    await session.flush()
    await session.refresh(tpl)
    return tpl


async def _make_instance(
    session,
    user_id: int,
    template_id: int,
    account_id: int,
    *,
    name: str = "RSI-多",
    status: str = "running",
) -> StrategyInstance:
    inst = StrategyInstance(
        user_id=user_id,
        template_id=template_id,
        account_id=account_id,
        name=name,
        symbol="BTCUSDT",
        exchange="binance",
        direction="both",
        params={},
        risk_params={},
        status=status,
        workspace_state="running",
    )
    session.add(inst)
    await session.flush()
    await session.refresh(inst)
    return inst


async def _make_position(
    session,
    account_id: int,
    *,
    strategy_instance_id: int | None = None,
    status: str = "open",
    side: str = "long",
) -> Position:
    pos = Position(
        account_id=account_id,
        symbol="BTCUSDT",
        side=side,
        quantity=Decimal("0.1"),
        entry_price=Decimal("50000"),
        current_price=Decimal("51000"),
        status=status,
        strategy_instance_id=strategy_instance_id,
    )
    session.add(pos)
    await session.flush()
    await session.refresh(pos)
    return pos


def _filled_close_result() -> OrderResult:
    return OrderResult(
        exchange_order_id="EX-CLOSE-1",
        symbol="BTCUSDT",
        side="sell",
        order_type="market",
        quantity=Decimal("0.1"),
        price=None,
        status="filled",
        filled_quantity=Decimal("0.1"),
        avg_fill_price=Decimal("51000"),
    )


def _mock_close_adapter():
    adapter = MagicMock()
    adapter.create_order = AsyncMock(return_value=_filled_close_result())
    adapter.cancel_order = AsyncMock()
    adapter.create_stop_order = AsyncMock()
    adapter.get_balance = AsyncMock(return_value=[])
    adapter.get_order = AsyncMock(return_value=_filled_close_result())
    return adapter


def _patch_class_adapter(monkeypatch, adapter):
    """让所有 OrderService 实例都用同一个 mock adapter。"""

    async def _get(self, account, **kwargs):
        return adapter

    monkeypatch.setattr(OrderService, "_get_adapter", _get)


# ==================== AssetService.get_positions 字段 ====================


class TestGetPositionsFields:
    async def test_external_position_marked_source_external(self, db_session):
        user = await _make_user(db_session, email="ext@example.com")
        account = await _make_account(db_session, user.id)
        await _make_position(db_session, account.id, strategy_instance_id=None)
        await db_session.commit()

        service = AssetService(db_session)
        positions = await service.get_positions(user_id=user.id)

        assert len(positions) == 1
        p = positions[0]
        assert p["source"] == "external"
        assert p["strategyInstanceId"] is None
        assert p["strategyName"] is None
        assert isinstance(p["positionId"], int)
        assert p["accountId"] == account.id
        assert p["accountName"] == "共用账户"

    async def test_strategy_position_includes_name(self, db_session):
        user = await _make_user(db_session, email="strat@example.com")
        account = await _make_account(db_session, user.id)
        tpl = await _make_template(db_session)
        inst = await _make_instance(db_session, user.id, tpl.id, account.id, name="RSI-做多")
        await _make_position(db_session, account.id, strategy_instance_id=inst.id)
        await db_session.commit()

        service = AssetService(db_session)
        positions = await service.get_positions(user_id=user.id)

        assert len(positions) == 1
        p = positions[0]
        assert p["source"] == "strategy"
        assert p["strategyInstanceId"] == inst.id
        assert p["strategyName"] == "RSI-做多"

    async def test_filter_by_account_id(self, db_session):
        user = await _make_user(db_session, email="filter@example.com")
        account_a = await _make_account(db_session, user.id, exchange="binance")
        account_b = await _make_account(db_session, user.id, exchange="okx")
        await _make_position(db_session, account_a.id)
        await _make_position(db_session, account_b.id)
        await db_session.commit()

        service = AssetService(db_session)
        only_a = await service.get_positions(user_id=user.id, account_id=account_a.id)
        assert len(only_a) == 1
        assert only_a[0]["accountId"] == account_a.id


# ==================== POST /trading/positions/{id}/close ====================


class TestClosePositionAPI:
    async def test_close_external_position_succeeds(
        self,
        client: AsyncClient,
        db_session,
        test_user,
        auth_headers,
        monkeypatch,
    ):
        account = await _make_account(db_session, test_user.id)
        position = await _make_position(db_session, account.id, strategy_instance_id=None)
        await db_session.commit()

        adapter = _mock_close_adapter()
        _patch_class_adapter(monkeypatch, adapter)

        resp = await client.post(
            f"/api/v1/trading/positions/{position.id}/close",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["positionId"] == position.id
        assert body["strategyInstanceId"] is None
        assert body["instancePaused"] is False

        adapter.create_order.assert_awaited()  # 确实下了对冲单

    async def test_close_strategy_position_pauses_instance(
        self,
        client: AsyncClient,
        db_session,
        test_user,
        auth_headers,
        monkeypatch,
    ):
        account = await _make_account(db_session, test_user.id)
        tpl = await _make_template(db_session)
        inst = await _make_instance(db_session, test_user.id, tpl.id, account.id, status="running")
        position = await _make_position(db_session, account.id, strategy_instance_id=inst.id)
        await db_session.commit()

        adapter = _mock_close_adapter()
        _patch_class_adapter(monkeypatch, adapter)

        resp = await client.post(
            f"/api/v1/trading/positions/{position.id}/close",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["strategyInstanceId"] == inst.id
        assert body["instancePaused"] is True

        await db_session.refresh(inst)
        assert inst.status == "paused"
        assert inst.last_pause_reason == "manual_close_via_ui"

    async def test_close_already_closed_returns_400(
        self,
        client: AsyncClient,
        db_session,
        test_user,
        auth_headers,
        monkeypatch,
    ):
        account = await _make_account(db_session, test_user.id)
        position = await _make_position(db_session, account.id, status="closed")
        await db_session.commit()

        adapter = _mock_close_adapter()
        _patch_class_adapter(monkeypatch, adapter)

        resp = await client.post(
            f"/api/v1/trading/positions/{position.id}/close",
            headers=auth_headers,
        )
        assert resp.status_code == 400

    async def test_close_other_user_position_returns_403(
        self,
        client: AsyncClient,
        db_session,
        test_user,
        auth_headers,
        monkeypatch,
    ):
        other = await _make_user(db_session, email="other@example.com")
        account = await _make_account(db_session, other.id)
        position = await _make_position(db_session, account.id)
        await db_session.commit()

        adapter = _mock_close_adapter()
        _patch_class_adapter(monkeypatch, adapter)

        resp = await client.post(
            f"/api/v1/trading/positions/{position.id}/close",
            headers=auth_headers,
        )
        assert resp.status_code == 403

    async def test_close_strategy_position_updates_stats(
        self,
        client: AsyncClient,
        db_session,
        test_user,
        auth_headers,
        monkeypatch,
    ):
        """平掉策略仓 → instance.total_trades / total_pnl / win_rate 同事务回写。"""
        account = await _make_account(db_session, test_user.id)
        tpl = await _make_template(db_session)
        inst = await _make_instance(db_session, test_user.id, tpl.id, account.id)
        # _make_position 默认 long, entry=50000, qty=0.1; mock fill price=51000
        # 预期 realized_pnl = (51000-50000) * 0.1 = 100
        position = await _make_position(db_session, account.id, strategy_instance_id=inst.id)
        await db_session.commit()
        assert inst.total_trades == 0
        assert inst.total_pnl == Decimal("0")

        adapter = _mock_close_adapter()
        _patch_class_adapter(monkeypatch, adapter)

        resp = await client.post(
            f"/api/v1/trading/positions/{position.id}/close",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        await db_session.refresh(inst)
        assert inst.total_trades == 1
        assert inst.total_pnl == Decimal("100.00000000")
        assert inst.win_rate == Decimal("100.00")  # 单笔盈利 → 100% 胜率

        # 平仓订单的 pnl 字段必须同步落库（绩效报告依赖 orders.pnl 计算高级指标）
        from sqlalchemy import select

        closing_order = (
            await db_session.execute(
                select(Order)
                .where(Order.strategy_instance_id == inst.id)
                .order_by(Order.id.desc())
                .limit(1)
            )
        ).scalar_one()
        assert closing_order.pnl == Decimal("100.00000000")

    async def test_external_close_does_not_touch_stats(
        self,
        client: AsyncClient,
        db_session,
        test_user,
        auth_headers,
        monkeypatch,
    ):
        """外部仓（strategy_instance_id=None）平仓不应影响任何策略统计。"""
        account = await _make_account(db_session, test_user.id)
        tpl = await _make_template(db_session)
        # 一个无关联仓位的策略实例 —— 它的 stats 应保持原样
        inst = await _make_instance(db_session, test_user.id, tpl.id, account.id)
        inst.total_trades = 5
        inst.total_pnl = Decimal("50")
        inst.win_rate = Decimal("60.00")
        position = await _make_position(db_session, account.id, strategy_instance_id=None)
        await db_session.commit()

        adapter = _mock_close_adapter()
        _patch_class_adapter(monkeypatch, adapter)

        resp = await client.post(
            f"/api/v1/trading/positions/{position.id}/close",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        await db_session.refresh(inst)
        assert inst.total_trades == 5
        assert inst.total_pnl == Decimal("50")
        assert inst.win_rate == Decimal("60.00")
