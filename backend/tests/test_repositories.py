"""
Repository 层测试 — 直接对接内存 SQLite，验证 CRUD 与定制查询
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio

from app.core.security import hash_password
from app.models.exchange import ExchangeAccount, Position
from app.models.order import Order, Signal
from app.models.strategy import StrategyInstance, StrategyTemplate
from app.models.user import User
from app.repositories.strategy_repo import (
    StrategyInstanceRepository,
    StrategyTemplateRepository,
)
from app.repositories.trading_repo import (
    ExchangeAccountRepository,
    OrderRepository,
    PositionRepository,
    SignalRepository,
)
from app.repositories.user_repo import UserRepository


# ==================== 通用工厂 ====================

async def _make_user(
    session, *, email: str = "u@example.com", name: str = "u"
) -> User:
    user = User(
        email=email,
        name=name,
        hashed_password=hash_password("password123"),
        status="active",
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def _make_account(
    session, user_id: int, *, exchange: str = "binance", active: bool = True
) -> ExchangeAccount:
    account = ExchangeAccount(
        user_id=user_id,
        exchange=exchange,
        account_name=f"{exchange}-acct",
        encrypted_api_key="x" * 32,
        encrypted_secret_key="y" * 32,
        is_active=active,
        status="active",
    )
    session.add(account)
    await session.flush()
    await session.refresh(account)
    return account


async def _make_template(
    session, *, code: str = "ma_cross", strategy_type: str = "ma", active: bool = True
) -> StrategyTemplate:
    tpl = StrategyTemplate(
        code=code,
        name=f"{code}-name",
        description="desc",
        strategy_type=strategy_type,
        params_schema={},
        risk_level="medium",
        is_active=active,
    )
    session.add(tpl)
    await session.flush()
    await session.refresh(tpl)
    return tpl


async def _make_instance(
    session,
    user_id: int,
    template_id: int,
    *,
    symbol: str = "BTCUSDT",
    status: str = "running",
) -> StrategyInstance:
    inst = StrategyInstance(
        user_id=user_id,
        template_id=template_id,
        name="my-strategy",
        symbol=symbol,
        exchange="binance",
        direction="both",
        params={},
        risk_params={},
        status=status,
    )
    session.add(inst)
    await session.flush()
    await session.refresh(inst)
    return inst


# ==================== UserRepository ====================

class TestUserRepository:
    async def test_create_and_get_by_id(self, db_session):
        repo = UserRepository(db_session)
        user = await _make_user(db_session, email="alice@example.com")
        fetched = await repo.get_by_id(user.id)
        assert fetched is not None
        assert fetched.email == "alice@example.com"

    async def test_get_by_email(self, db_session):
        repo = UserRepository(db_session)
        await _make_user(db_session, email="bob@example.com")
        fetched = await repo.get_by_email("bob@example.com")
        assert fetched is not None
        assert fetched.email == "bob@example.com"

    async def test_get_by_email_returns_none_for_missing(self, db_session):
        repo = UserRepository(db_session)
        assert await repo.get_by_email("missing@nowhere.com") is None

    async def test_email_exists(self, db_session):
        repo = UserRepository(db_session)
        await _make_user(db_session, email="exists@example.com")
        assert await repo.email_exists("exists@example.com") is True
        assert await repo.email_exists("nope@example.com") is False

    async def test_get_by_email_with_accounts_eager_loads(self, db_session):
        repo = UserRepository(db_session)
        user = await _make_user(db_session, email="trader@example.com")
        await _make_account(db_session, user.id, exchange="binance")
        await _make_account(db_session, user.id, exchange="okx")
        # 强制清掉 session 缓存，确保 selectinload 生效
        db_session.expire_all()

        fetched = await repo.get_by_email_with_accounts("trader@example.com")
        assert fetched is not None
        # accounts 已被 selectinload 加载
        assert len(fetched.accounts) == 2

    async def test_count(self, db_session):
        repo = UserRepository(db_session)
        before = await repo.count()
        await _make_user(db_session, email="count1@example.com")
        await _make_user(db_session, email="count2@example.com")
        after = await repo.count()
        assert after == before + 2

    async def test_update(self, db_session):
        repo = UserRepository(db_session)
        user = await _make_user(db_session, email="upd@example.com", name="old")
        updated = await repo.update(user.id, name="new-name")
        assert updated is not None
        assert updated.name == "new-name"

    async def test_delete(self, db_session):
        repo = UserRepository(db_session)
        user = await _make_user(db_session, email="del@example.com")
        deleted = await repo.delete(user.id)
        assert deleted is True
        assert await repo.get_by_id(user.id) is None

    async def test_exists(self, db_session):
        repo = UserRepository(db_session)
        user = await _make_user(db_session, email="ex@example.com")
        assert await repo.exists(user.id) is True
        assert await repo.exists(999_999) is False


# ==================== ExchangeAccountRepository ====================

class TestExchangeAccountRepository:
    async def test_get_by_user_returns_all(self, db_session):
        repo = ExchangeAccountRepository(db_session)
        user = await _make_user(db_session, email="multi@example.com")
        await _make_account(db_session, user.id, exchange="binance")
        await _make_account(db_session, user.id, exchange="okx", active=False)

        accounts = await repo.get_by_user(user.id)
        assert len(accounts) == 2

    async def test_get_active_by_user_filters_inactive(self, db_session):
        repo = ExchangeAccountRepository(db_session)
        user = await _make_user(db_session, email="active@example.com")
        await _make_account(db_session, user.id, exchange="binance", active=True)
        await _make_account(db_session, user.id, exchange="okx", active=False)

        accounts = await repo.get_active_by_user(user.id)
        assert len(accounts) == 1
        assert accounts[0].exchange == "binance"

    async def test_get_by_user_and_exchange(self, db_session):
        repo = ExchangeAccountRepository(db_session)
        user = await _make_user(db_session, email="byex@example.com")
        await _make_account(db_session, user.id, exchange="binance")

        found = await repo.get_by_user_and_exchange(user.id, "binance")
        missing = await repo.get_by_user_and_exchange(user.id, "okx")
        assert found is not None
        assert found.exchange == "binance"
        assert missing is None


# ==================== PositionRepository ====================

async def _make_position(
    session,
    account_id: int,
    *,
    symbol: str = "BTCUSDT",
    side: str = "long",
    status: str = "open",
    quantity: str = "1",
    entry_price: str = "50000",
    current_price: str = "50000",
    strategy_instance_id: int | None = None,
) -> Position:
    pos = Position(
        account_id=account_id,
        symbol=symbol,
        side=side,
        quantity=Decimal(quantity),
        entry_price=Decimal(entry_price),
        current_price=Decimal(current_price),
        status=status,
        strategy_instance_id=strategy_instance_id,
    )
    session.add(pos)
    await session.flush()
    await session.refresh(pos)
    return pos


class TestPositionRepository:
    async def test_get_open_by_account_filters_closed(self, db_session):
        repo = PositionRepository(db_session)
        user = await _make_user(db_session, email="pos@example.com")
        account = await _make_account(db_session, user.id)
        await _make_position(db_session, account.id, status="open")
        await _make_position(db_session, account.id, status="closed")

        positions = await repo.get_open_by_account(account.id)
        assert len(positions) == 1
        assert positions[0].status == "open"

    async def test_get_by_account_and_symbol(self, db_session):
        repo = PositionRepository(db_session)
        user = await _make_user(db_session, email="bysym@example.com")
        account = await _make_account(db_session, user.id)
        await _make_position(db_session, account.id, symbol="BTCUSDT")
        await _make_position(db_session, account.id, symbol="ETHUSDT")

        btc = await repo.get_by_account_and_symbol(account.id, "BTCUSDT")
        assert len(btc) == 1
        assert btc[0].symbol == "BTCUSDT"

    async def test_get_by_strategy(self, db_session):
        repo = PositionRepository(db_session)
        user = await _make_user(db_session, email="bystrat@example.com")
        account = await _make_account(db_session, user.id)
        tpl = await _make_template(db_session, code="rsi_test_strategy")
        inst = await _make_instance(db_session, user.id, tpl.id)
        await _make_position(
            db_session, account.id, strategy_instance_id=inst.id
        )
        await _make_position(db_session, account.id, strategy_instance_id=None)

        result = await repo.get_by_strategy(inst.id)
        assert len(result) == 1
        assert result[0].strategy_instance_id == inst.id

    async def test_get_total_exposure(self, db_session):
        repo = PositionRepository(db_session)
        user = await _make_user(db_session, email="exposure@example.com")
        account = await _make_account(db_session, user.id)
        await _make_position(
            db_session, account.id, quantity="2", current_price="100"
        )
        await _make_position(
            db_session, account.id, quantity="1", current_price="50"
        )
        # Closed 仓位不计入
        await _make_position(
            db_session, account.id, quantity="100", current_price="100",
            status="closed",
        )

        exposure = await repo.get_total_exposure(account.id)
        assert exposure == Decimal("250")  # 2*100 + 1*50

    async def test_get_total_exposure_filtered_by_symbol(self, db_session):
        repo = PositionRepository(db_session)
        user = await _make_user(db_session, email="exposure2@example.com")
        account = await _make_account(db_session, user.id)
        await _make_position(
            db_session, account.id, symbol="BTCUSDT",
            quantity="1", current_price="100",
        )
        await _make_position(
            db_session, account.id, symbol="ETHUSDT",
            quantity="10", current_price="10",
        )

        btc_exposure = await repo.get_total_exposure(account.id, "BTCUSDT")
        assert btc_exposure == Decimal("100")


# ==================== OrderRepository ====================

async def _make_order(
    session,
    account_id: int,
    *,
    symbol: str = "BTCUSDT",
    side: str = "buy",
    status: str = "pending",
    exchange_order_id: str | None = None,
    strategy_instance_id: int | None = None,
    quantity: str = "1",
) -> Order:
    order = Order(
        account_id=account_id,
        symbol=symbol,
        side=side,
        order_type="market",
        quantity=Decimal(quantity),
        filled_quantity=Decimal("0"),
        order_value=Decimal("0"),
        status=status,
        exchange_order_id=exchange_order_id,
        strategy_instance_id=strategy_instance_id,
    )
    session.add(order)
    await session.flush()
    await session.refresh(order)
    return order


class TestOrderRepository:
    async def test_get_by_account_returns_all_orders(self, db_session):
        repo = OrderRepository(db_session)
        user = await _make_user(db_session, email="ord@example.com")
        account = await _make_account(db_session, user.id)
        o1 = await _make_order(db_session, account.id)
        o2 = await _make_order(db_session, account.id)

        result = await repo.get_by_account(account.id)
        ids = {o.id for o in result}
        assert ids == {o1.id, o2.id}

    async def test_get_by_account_with_status_filter(self, db_session):
        repo = OrderRepository(db_session)
        user = await _make_user(db_session, email="ordstat@example.com")
        account = await _make_account(db_session, user.id)
        await _make_order(db_session, account.id, status="filled")
        await _make_order(db_session, account.id, status="pending")

        filled = await repo.get_by_account(account.id, status="filled")
        assert len(filled) == 1
        assert filled[0].status == "filled"

    async def test_get_by_account_limit(self, db_session):
        repo = OrderRepository(db_session)
        user = await _make_user(db_session, email="ordlim@example.com")
        account = await _make_account(db_session, user.id)
        for _ in range(5):
            await _make_order(db_session, account.id)

        result = await repo.get_by_account(account.id, limit=3)
        assert len(result) == 3

    async def test_get_pending_orders(self, db_session):
        repo = OrderRepository(db_session)
        user = await _make_user(db_session, email="ordpend@example.com")
        account = await _make_account(db_session, user.id)
        await _make_order(db_session, account.id, status="pending")
        await _make_order(db_session, account.id, status="submitted")
        await _make_order(db_session, account.id, status="partial")
        await _make_order(db_session, account.id, status="filled")
        await _make_order(db_session, account.id, status="cancelled")

        pending = await repo.get_pending_orders(account.id)
        assert len(pending) == 3
        assert {o.status for o in pending} == {
            "pending",
            "submitted",
            "partial",
        }

    async def test_get_by_exchange_order_id(self, db_session):
        repo = OrderRepository(db_session)
        user = await _make_user(db_session, email="ordex@example.com")
        account = await _make_account(db_session, user.id)
        await _make_order(
            db_session, account.id, exchange_order_id="EX-12345"
        )

        found = await repo.get_by_exchange_order_id("EX-12345")
        missing = await repo.get_by_exchange_order_id("EX-NOT-EXIST")
        assert found is not None
        assert found.exchange_order_id == "EX-12345"
        assert missing is None

    async def test_get_by_strategy(self, db_session):
        repo = OrderRepository(db_session)
        user = await _make_user(db_session, email="ordstr@example.com")
        account = await _make_account(db_session, user.id)
        tpl = await _make_template(db_session, code="ord_strategy_tpl")
        inst = await _make_instance(db_session, user.id, tpl.id)

        await _make_order(
            db_session, account.id, strategy_instance_id=inst.id
        )
        await _make_order(db_session, account.id, strategy_instance_id=None)

        result = await repo.get_by_strategy(inst.id)
        assert len(result) == 1


# ==================== SignalRepository ====================

class TestSignalRepository:
    async def test_get_pending_by_strategy(self, db_session):
        repo = SignalRepository(db_session)
        user = await _make_user(db_session, email="sig@example.com")
        tpl = await _make_template(db_session, code="sig_tpl")
        inst = await _make_instance(db_session, user.id, tpl.id)

        pending = Signal(
            strategy_instance_id=inst.id,
            symbol="BTCUSDT",
            action="buy",
            confidence=Decimal("0.8"),
            status="pending",
        )
        executed = Signal(
            strategy_instance_id=inst.id,
            symbol="BTCUSDT",
            action="buy",
            confidence=Decimal("0.9"),
            status="executed",
        )
        db_session.add_all([pending, executed])
        await db_session.flush()

        result = await repo.get_pending_by_strategy(inst.id)
        assert len(result) == 1
        assert result[0].status == "pending"

    async def test_expire_old_signals(self, db_session):
        repo = SignalRepository(db_session)
        user = await _make_user(db_session, email="sigexp@example.com")
        tpl = await _make_template(db_session, code="sigexp_tpl")
        inst = await _make_instance(db_session, user.id, tpl.id)

        past = datetime.now(timezone.utc) - timedelta(hours=1)
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        db_session.add_all([
            Signal(
                strategy_instance_id=inst.id, symbol="BTCUSDT", action="buy",
                confidence=Decimal("0.8"), status="pending", expires_at=past,
            ),
            Signal(
                strategy_instance_id=inst.id, symbol="BTCUSDT", action="buy",
                confidence=Decimal("0.8"), status="pending", expires_at=future,
            ),
        ])
        await db_session.flush()

        expired_count = await repo.expire_old_signals(inst.id)
        assert expired_count == 1


# ==================== StrategyTemplateRepository ====================

class TestStrategyTemplateRepository:
    async def test_get_active_templates(self, db_session):
        repo = StrategyTemplateRepository(db_session)
        await _make_template(db_session, code="tpl_active_1", active=True)
        await _make_template(db_session, code="tpl_inactive", active=False)
        await _make_template(db_session, code="tpl_active_2", active=True)

        active = await repo.get_active_templates()
        codes = {t.code for t in active}
        assert "tpl_active_1" in codes
        assert "tpl_active_2" in codes
        assert "tpl_inactive" not in codes

    async def test_get_by_type(self, db_session):
        repo = StrategyTemplateRepository(db_session)
        await _make_template(
            db_session, code="rsi_x", strategy_type="rsi_test_type"
        )
        result = await repo.get_by_type("rsi_test_type")
        assert result is not None
        assert result.strategy_type == "rsi_test_type"

    async def test_get_by_type_returns_none_when_inactive(self, db_session):
        repo = StrategyTemplateRepository(db_session)
        await _make_template(
            db_session,
            code="bollinger_x",
            strategy_type="bollinger_only_inactive",
            active=False,
        )
        # 即使存在但非 active 也返回 None
        assert await repo.get_by_type("bollinger_only_inactive") is None

    async def test_get_by_code(self, db_session):
        repo = StrategyTemplateRepository(db_session)
        await _make_template(db_session, code="grid_test")
        result = await repo.get_by_code("grid_test")
        assert result is not None
        assert result.code == "grid_test"
        assert await repo.get_by_code("missing-code") is None


# ==================== StrategyInstanceRepository ====================

class TestStrategyInstanceRepository:
    async def test_get_by_user(self, db_session):
        repo = StrategyInstanceRepository(db_session)
        user_a = await _make_user(db_session, email="usera@example.com")
        user_b = await _make_user(db_session, email="userb@example.com")
        tpl = await _make_template(db_session, code="multi_user_tpl")
        await _make_instance(db_session, user_a.id, tpl.id)
        await _make_instance(db_session, user_a.id, tpl.id)
        await _make_instance(db_session, user_b.id, tpl.id)

        a_instances = await repo.get_by_user(user_a.id)
        b_instances = await repo.get_by_user(user_b.id)
        assert len(a_instances) == 2
        assert len(b_instances) == 1

    async def test_get_active_by_user_only_running(self, db_session):
        repo = StrategyInstanceRepository(db_session)
        user = await _make_user(db_session, email="runonly@example.com")
        tpl = await _make_template(db_session, code="runonly_tpl")
        await _make_instance(db_session, user.id, tpl.id, status="running")
        await _make_instance(db_session, user.id, tpl.id, status="paused")
        await _make_instance(db_session, user.id, tpl.id, status="stopped")

        active = await repo.get_active_by_user(user.id)
        assert len(active) == 1
        assert active[0].status == "running"

    async def test_get_by_user_and_symbol(self, db_session):
        repo = StrategyInstanceRepository(db_session)
        user = await _make_user(db_session, email="bysymbol@example.com")
        tpl = await _make_template(db_session, code="bysymbol_tpl")
        await _make_instance(db_session, user.id, tpl.id, symbol="BTCUSDT")
        await _make_instance(db_session, user.id, tpl.id, symbol="ETHUSDT")

        btc = await repo.get_by_user_and_symbol(user.id, "BTCUSDT")
        assert len(btc) == 1
        assert btc[0].symbol == "BTCUSDT"

    async def test_get_with_template_eager_loads(self, db_session):
        repo = StrategyInstanceRepository(db_session)
        user = await _make_user(db_session, email="withtpl@example.com")
        tpl = await _make_template(db_session, code="withtpl_tpl")
        inst = await _make_instance(db_session, user.id, tpl.id)

        fetched = await repo.get_with_template(inst.id)
        assert fetched is not None
        # template 已被 selectinload 加载
        assert fetched.template is not None
        assert fetched.template.code == "withtpl_tpl"
