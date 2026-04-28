"""
OrderService 测试 — 核心订单生命周期、止盈止损、紧急平仓

通过替换 OrderService._get_adapter，避免对真实交易所的依赖。
"""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.core.exceptions import (
    NetworkError,
    OrderRejectedError,
    RateLimitError,
)
from app.core.exchanges.base import Balance, OrderResult
from app.core.security import hash_password
from app.models.exchange import ExchangeAccount, Position
from app.models.user import User
from app.services.order_service import OrderService


# ==================== Helpers ====================

async def _make_user(session, *, email: str = "svc@example.com") -> User:
    user = User(
        email=email,
        name="svcuser",
        hashed_password=hash_password("password123"),
        status="active",
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def _make_account(
    session, user_id: int, *, active: bool = True, exchange: str = "binance"
) -> ExchangeAccount:
    """创建一个交易所账户，使用真实的加密 API Key（让 get_api_key/decrypt 不报错）"""
    account = ExchangeAccount(
        user_id=user_id,
        exchange=exchange,
        account_name="test-account",
        is_active=active,
        status="active",
    )
    account.set_api_key("FAKE_API_KEY_FOR_TEST_AAAAA")
    account.set_secret_key("FAKE_SECRET_KEY_FOR_TEST_BBBBB")
    session.add(account)
    await session.flush()
    await session.refresh(account)
    return account


async def _make_position(
    session,
    account_id: int,
    *,
    symbol: str = "BTCUSDT",
    side: str = "long",
    status: str = "open",
    quantity: str = "1",
    entry_price: str = "50000",
) -> Position:
    pos = Position(
        account_id=account_id,
        symbol=symbol,
        side=side,
        quantity=Decimal(quantity),
        entry_price=Decimal(entry_price),
        current_price=Decimal(entry_price),
        status=status,
    )
    session.add(pos)
    await session.flush()
    await session.refresh(pos)
    return pos


def _mock_adapter(create_result: OrderResult | Exception | None = None):
    """构建一个 mock adapter，create_order 返回 result 或抛出异常"""
    adapter = MagicMock()
    adapter.create_order = AsyncMock()
    adapter.cancel_order = AsyncMock()
    adapter.create_stop_order = AsyncMock()
    adapter.get_balance = AsyncMock()

    if isinstance(create_result, Exception):
        adapter.create_order.side_effect = create_result
    elif create_result is not None:
        adapter.create_order.return_value = create_result

    return adapter


def _patch_adapter(service: OrderService, adapter):
    """替换 service._get_adapter"""
    async def _get(_):
        return adapter
    service._get_adapter = _get  # type: ignore[method-assign]


def _filled_order_result(qty: str = "0.01", price: str = "50000") -> OrderResult:
    return OrderResult(
        exchange_order_id="EX-123",
        symbol="BTCUSDT",
        side="buy",
        order_type="market",
        quantity=Decimal(qty),
        price=None,
        status="filled",
        filled_quantity=Decimal(qty),
        avg_fill_price=Decimal(price),
    )


# ==================== create_order 校验 ====================

class TestCreateOrder:
    async def test_create_order_success(self, db_session):
        user = await _make_user(db_session, email="cr1@example.com")
        account = await _make_account(db_session, user.id)
        service = OrderService(db_session)

        order = await service.create_order(
            user_id=user.id,
            account_id=account.id,
            symbol="btcusdt",
            side="buy",
            order_type="market",
            quantity=Decimal("0.01"),
        )
        assert order.id is not None
        assert order.status == "pending"
        assert order.symbol == "BTCUSDT"  # 自动 upper

    async def test_create_order_with_limit_price(self, db_session):
        user = await _make_user(db_session, email="cr2@example.com")
        account = await _make_account(db_session, user.id)
        service = OrderService(db_session)

        order = await service.create_order(
            user_id=user.id,
            account_id=account.id,
            symbol="BTCUSDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
        )
        # order_value = 0.01 * 50000 = 500
        assert order.order_value == Decimal("500")

    async def test_create_order_market_zero_value(self, db_session):
        user = await _make_user(db_session, email="cr3@example.com")
        account = await _make_account(db_session, user.id)
        service = OrderService(db_session)

        order = await service.create_order(
            user_id=user.id,
            account_id=account.id,
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=Decimal("0.01"),
        )
        # 市价单提交前 value=0，等真实成交后由交易所返回价更新
        assert order.order_value == Decimal("0")

    async def test_create_order_rejects_other_users_account(self, db_session):
        user_a = await _make_user(db_session, email="cra@example.com")
        user_b = await _make_user(db_session, email="crb@example.com")
        account_b = await _make_account(db_session, user_b.id)
        service = OrderService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_order(
                user_id=user_a.id,
                account_id=account_b.id,
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=Decimal("0.01"),
            )
        assert exc_info.value.status_code == 404

    async def test_create_order_rejects_disabled_account(self, db_session):
        user = await _make_user(db_session, email="crd@example.com")
        account = await _make_account(db_session, user.id, active=False)
        service = OrderService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_order(
                user_id=user.id,
                account_id=account.id,
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=Decimal("0.01"),
            )
        assert exc_info.value.status_code == 400


# ==================== submit_order 异常分类 ====================

class TestSubmitOrder:
    async def test_submit_order_success_marks_filled(self, db_session):
        user = await _make_user(db_session, email="sub1@example.com")
        account = await _make_account(db_session, user.id)
        service = OrderService(db_session)
        order = await service.create_order(
            user_id=user.id,
            account_id=account.id,
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=Decimal("0.01"),
        )
        adapter = _mock_adapter(create_result=_filled_order_result())
        _patch_adapter(service, adapter)

        result = await service.submit_order(order.id, user.id)
        assert result.status == "filled"
        assert result.exchange_order_id == "EX-123"
        assert result.filled_quantity == Decimal("0.01")
        assert result.filled_at is not None
        adapter.create_order.assert_awaited_once()

    async def test_submit_order_rejected_marks_status(self, db_session):
        user = await _make_user(db_session, email="sub2@example.com")
        account = await _make_account(db_session, user.id)
        service = OrderService(db_session)
        order = await service.create_order(
            user_id=user.id, account_id=account.id, symbol="BTCUSDT",
            side="buy", order_type="market", quantity=Decimal("0.01"),
        )
        adapter = _mock_adapter(
            create_result=OrderRejectedError("binance", "余额不足", "INSUFFICIENT")
        )
        _patch_adapter(service, adapter)

        with pytest.raises(HTTPException) as exc_info:
            await service.submit_order(order.id, user.id)
        assert exc_info.value.status_code == 400
        # 订单已被标记为 rejected
        await db_session.refresh(order)
        assert order.status == "rejected"
        assert "余额不足" in (order.error_message or "")

    async def test_submit_order_rate_limit_returns_429(self, db_session):
        user = await _make_user(db_session, email="sub3@example.com")
        account = await _make_account(db_session, user.id)
        service = OrderService(db_session)
        order = await service.create_order(
            user_id=user.id, account_id=account.id, symbol="BTCUSDT",
            side="buy", order_type="market", quantity=Decimal("0.01"),
        )
        adapter = _mock_adapter(
            create_result=RateLimitError("binance")
        )
        _patch_adapter(service, adapter)

        with pytest.raises(HTTPException) as exc_info:
            await service.submit_order(order.id, user.id)
        assert exc_info.value.status_code == 429
        # 限流场景不应改变订单状态，让前端可以重试
        await db_session.refresh(order)
        assert order.status == "pending"

    async def test_submit_order_network_error_returns_502(self, db_session):
        user = await _make_user(db_session, email="sub4@example.com")
        account = await _make_account(db_session, user.id)
        service = OrderService(db_session)
        order = await service.create_order(
            user_id=user.id, account_id=account.id, symbol="BTCUSDT",
            side="buy", order_type="market", quantity=Decimal("0.01"),
        )
        adapter = _mock_adapter(
            create_result=NetworkError("binance", "连接超时")
        )
        _patch_adapter(service, adapter)

        with pytest.raises(HTTPException) as exc_info:
            await service.submit_order(order.id, user.id)
        assert exc_info.value.status_code == 502
        # 网络异常下保留 pending 状态以便核对，错误信息已写入
        await db_session.refresh(order)
        assert "网络" in (order.error_message or "")

    async def test_submit_order_not_found(self, db_session):
        user = await _make_user(db_session, email="sub5@example.com")
        service = OrderService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.submit_order(99999, user.id)
        assert exc_info.value.status_code == 404

    async def test_submit_order_other_user_forbidden(self, db_session):
        user_a = await _make_user(db_session, email="sub6a@example.com")
        user_b = await _make_user(db_session, email="sub6b@example.com")
        account = await _make_account(db_session, user_a.id)
        service = OrderService(db_session)
        order = await service.create_order(
            user_id=user_a.id, account_id=account.id, symbol="BTCUSDT",
            side="buy", order_type="market", quantity=Decimal("0.01"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.submit_order(order.id, user_b.id)
        assert exc_info.value.status_code == 403


# ==================== cancel_order ====================

class TestCancelOrder:
    async def test_cancel_pending_order_no_exchange_call(self, db_session):
        """没有 exchange_order_id 时直接本地标记为 cancelled"""
        user = await _make_user(db_session, email="can1@example.com")
        account = await _make_account(db_session, user.id)
        service = OrderService(db_session)
        order = await service.create_order(
            user_id=user.id, account_id=account.id, symbol="BTCUSDT",
            side="buy", order_type="market", quantity=Decimal("0.01"),
        )
        # 订单尚未提交到交易所，没 exchange_order_id
        cancelled = await service.cancel_order(order.id, user.id)
        assert cancelled.status == "cancelled"
        assert cancelled.cancelled_at is not None

    async def test_cancel_filled_order_rejected(self, db_session):
        user = await _make_user(db_session, email="can2@example.com")
        account = await _make_account(db_session, user.id)
        service = OrderService(db_session)
        order = await service.create_order(
            user_id=user.id, account_id=account.id, symbol="BTCUSDT",
            side="buy", order_type="market", quantity=Decimal("0.01"),
        )
        order.status = "filled"
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await service.cancel_order(order.id, user.id)
        assert exc_info.value.status_code == 400

    async def test_cancel_calls_exchange_when_submitted(self, db_session):
        user = await _make_user(db_session, email="can3@example.com")
        account = await _make_account(db_session, user.id)
        service = OrderService(db_session)
        order = await service.create_order(
            user_id=user.id, account_id=account.id, symbol="BTCUSDT",
            side="buy", order_type="market", quantity=Decimal("0.01"),
        )
        order.status = "submitted"
        order.exchange_order_id = "EX-CANCEL-1"
        await db_session.commit()

        adapter = _mock_adapter()
        adapter.cancel_order.return_value = True
        _patch_adapter(service, adapter)

        cancelled = await service.cancel_order(order.id, user.id)
        assert cancelled.status == "cancelled"
        adapter.cancel_order.assert_awaited_once_with("EX-CANCEL-1", "BTCUSDT")

    async def test_cancel_exchange_failure_502(self, db_session):
        user = await _make_user(db_session, email="can4@example.com")
        account = await _make_account(db_session, user.id)
        service = OrderService(db_session)
        order = await service.create_order(
            user_id=user.id, account_id=account.id, symbol="BTCUSDT",
            side="buy", order_type="market", quantity=Decimal("0.01"),
        )
        order.status = "submitted"
        order.exchange_order_id = "EX-CANCEL-2"
        await db_session.commit()

        adapter = _mock_adapter()
        adapter.cancel_order.return_value = False
        _patch_adapter(service, adapter)

        with pytest.raises(HTTPException) as exc_info:
            await service.cancel_order(order.id, user.id)
        assert exc_info.value.status_code == 502


# ==================== 止损/止盈价格校验 ====================

class TestStopLossValidation:
    async def test_long_stop_loss_must_be_below_entry(self, db_session):
        user = await _make_user(db_session, email="sl1@example.com")
        account = await _make_account(db_session, user.id)
        position = await _make_position(
            db_session, account.id, side="long", entry_price="50000"
        )
        service = OrderService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.set_stop_loss(
                position.id, user.id, Decimal("51000")
            )
        assert exc_info.value.status_code == 400

    async def test_short_stop_loss_must_be_above_entry(self, db_session):
        user = await _make_user(db_session, email="sl2@example.com")
        account = await _make_account(db_session, user.id)
        position = await _make_position(
            db_session, account.id, side="short", entry_price="50000"
        )
        service = OrderService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.set_stop_loss(
                position.id, user.id, Decimal("49000")
            )
        assert exc_info.value.status_code == 400

    async def test_set_stop_loss_falls_back_to_local_on_exchange_failure(
        self, db_session
    ):
        """交易所条件单失败应当降级为本地止损（不抛出）"""
        user = await _make_user(db_session, email="sl3@example.com")
        account = await _make_account(db_session, user.id)
        position = await _make_position(
            db_session, account.id, side="long", entry_price="50000"
        )
        service = OrderService(db_session)

        adapter = _mock_adapter()
        adapter.create_stop_order.side_effect = NetworkError(
            "binance", "条件单提交失败"
        )
        _patch_adapter(service, adapter)

        result = await service.set_stop_loss(
            position.id, user.id, Decimal("48000")
        )
        # 本地止损价仍然写入
        assert result.stop_loss_price == Decimal("48000")
        # 没有 exchange order id
        assert result.stop_loss_order_id is None

    async def test_set_stop_loss_saves_exchange_order_id(self, db_session):
        user = await _make_user(db_session, email="sl4@example.com")
        account = await _make_account(db_session, user.id)
        position = await _make_position(
            db_session, account.id, side="long", entry_price="50000"
        )
        service = OrderService(db_session)

        adapter = _mock_adapter()
        adapter.create_stop_order.return_value = OrderResult(
            exchange_order_id="EX-SL-1",
            symbol="BTCUSDT",
            side="sell",
            order_type="stop_loss",
            quantity=Decimal("1"),
            price=None,
            status="pending",
            filled_quantity=Decimal("0"),
            avg_fill_price=None,
        )
        _patch_adapter(service, adapter)

        result = await service.set_stop_loss(
            position.id, user.id, Decimal("48000")
        )
        assert result.stop_loss_order_id == "EX-SL-1"
        assert result.stop_loss_price == Decimal("48000")
        # 校验止损方向：long 持仓 → sell 止损
        adapter.create_stop_order.assert_awaited_once()
        call = adapter.create_stop_order.call_args
        assert call.kwargs["side"] == "sell"


class TestTakeProfitValidation:
    async def test_long_tp_must_be_above_entry(self, db_session):
        user = await _make_user(db_session, email="tp1@example.com")
        account = await _make_account(db_session, user.id)
        position = await _make_position(
            db_session, account.id, side="long", entry_price="50000"
        )
        service = OrderService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.set_take_profit(
                position.id, user.id, Decimal("49000")
            )
        assert exc_info.value.status_code == 400

    async def test_short_tp_must_be_below_entry(self, db_session):
        user = await _make_user(db_session, email="tp2@example.com")
        account = await _make_account(db_session, user.id)
        position = await _make_position(
            db_session, account.id, side="short", entry_price="50000"
        )
        service = OrderService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.set_take_profit(
                position.id, user.id, Decimal("51000")
            )
        assert exc_info.value.status_code == 400


# ==================== 平仓 ====================

class TestClosePosition:
    async def test_close_long_position_creates_sell_order(self, db_session):
        user = await _make_user(db_session, email="cp1@example.com")
        account = await _make_account(db_session, user.id)
        position = await _make_position(
            db_session, account.id, side="long", quantity="1"
        )
        service = OrderService(db_session)

        adapter = _mock_adapter(
            create_result=_filled_order_result(qty="1", price="50000")
        )
        _patch_adapter(service, adapter)

        closed = await service.close_position(position.id, user.id)
        assert closed.status == "closed"
        assert closed.closed_at is not None
        # 平仓订单方向应当与 position 相反
        call = adapter.create_order.call_args
        assert call.kwargs["side"] == "sell"

    async def test_close_already_closed_rejected(self, db_session):
        user = await _make_user(db_session, email="cp2@example.com")
        account = await _make_account(db_session, user.id)
        position = await _make_position(
            db_session, account.id, status="closed"
        )
        service = OrderService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.close_position(position.id, user.id)
        assert exc_info.value.status_code == 400


# ==================== 余额同步 ====================

class TestSyncAccountBalance:
    async def test_sync_writes_usdt_balance(self, db_session):
        user = await _make_user(db_session, email="sync1@example.com")
        account = await _make_account(db_session, user.id)
        service = OrderService(db_session)

        adapter = _mock_adapter()
        adapter.get_balance.return_value = [
            Balance(asset="BTC", free=Decimal("0.5"), locked=Decimal("0")),
            Balance(asset="USDT", free=Decimal("10000"), locked=Decimal("500")),
        ]
        _patch_adapter(service, adapter)

        synced = await service.sync_account_balance(account.id, user.id)
        assert synced.balance == Decimal("10000")
        assert synced.frozen_balance == Decimal("500")
        assert synced.status == "active"
        assert synced.last_sync_at is not None

    async def test_sync_records_error_on_failure(self, db_session):
        user = await _make_user(db_session, email="sync2@example.com")
        account = await _make_account(db_session, user.id)
        service = OrderService(db_session)

        adapter = _mock_adapter()
        adapter.get_balance.side_effect = NetworkError("binance", "连接失败")
        _patch_adapter(service, adapter)

        with pytest.raises(HTTPException) as exc_info:
            await service.sync_account_balance(account.id, user.id)
        assert exc_info.value.status_code == 502
        await db_session.refresh(account)
        assert account.status == "error"
        assert "余额同步失败" in (account.error_message or "")

    async def test_sync_other_user_forbidden(self, db_session):
        user_a = await _make_user(db_session, email="sync3a@example.com")
        user_b = await _make_user(db_session, email="sync3b@example.com")
        account_a = await _make_account(db_session, user_a.id)
        service = OrderService(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await service.sync_account_balance(account_a.id, user_b.id)
        assert exc_info.value.status_code == 403
