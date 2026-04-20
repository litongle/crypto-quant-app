"""
订单服务
"""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.exchange import ExchangeAccount, Position
from app.models.order import Order
from app.models.strategy import StrategyInstance
from app.repositories.trading_repo import (
    ExchangeAccountRepository,
    PositionRepository,
    OrderRepository,
)
from app.repositories.strategy_repo import StrategyInstanceRepository


class OrderService:
    """订单服务"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.account_repo = ExchangeAccountRepository(session)
        self.position_repo = PositionRepository(session)
        self.order_repo = OrderRepository(session)
        self.strategy_repo = StrategyInstanceRepository(session)

    async def get_user_accounts(self, user_id: int) -> list[ExchangeAccount]:
        """获取用户的交易所账户"""
        return await self.account_repo.get_active_by_user(user_id)

    async def create_order(
        self,
        user_id: int,
        account_id: int,
        symbol: str,
        side: Literal["buy", "sell"],
        order_type: Literal["market", "limit"],
        quantity: Decimal,
        price: Decimal | None = None,
        strategy_instance_id: int | None = None,
    ) -> Order:
        """
        创建订单
        """
        # 验证账户
        account = await self.account_repo.get_by_id(account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="账户不存在",
            )
        if not account.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="账户已禁用",
            )

        # 验证策略（如果指定）
        if strategy_instance_id:
            strategy = await self.strategy_repo.get_by_id(strategy_instance_id)
            if not strategy or strategy.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="策略不存在",
                )

        # 计算订单价值
        if order_type == "market":
            # 市价单：标记为待计算，提交到交易所后根据成交价更新
            order_value = Decimal("0")  # 提交后由交易所返回的实际成交价计算
        elif price and price > 0:
            order_value = quantity * price
        else:
            order_value = Decimal("0")

        # 创建订单
        order = Order(
            account_id=account_id,
            symbol=symbol.upper(),
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            order_value=order_value,
            status="pending",
            strategy_instance_id=strategy_instance_id,
        )
        return await self.order_repo.create(order)

    async def submit_order(self, order_id: int, user_id: int) -> Order:
        """提交订单到交易所（模拟实现）"""
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="订单不存在",
            )

        account = await self.account_repo.get_by_id(order.account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作此订单",
            )

        order.status = "submitted"
        order.submitted_at = datetime.utcnow()
        await self.session.commit()
        return order

    async def cancel_order(self, order_id: int, user_id: int) -> Order:
        """取消订单"""
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="订单不存在",
            )

        account = await self.account_repo.get_by_id(order.account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作此订单",
            )

        if order.status not in ["pending", "submitted", "partial"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"订单状态{order.status}无法取消",
            )

        order.status = "cancelled"
        order.cancelled_at = datetime.utcnow()
        await self.session.commit()
        return order

    async def get_order_history(
        self,
        user_id: int,
        account_id: int | None = None,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[Order]:
        """获取订单历史"""
        accounts = await self.account_repo.get_active_by_user(user_id)
        if not accounts:
            return []

        all_orders = []
        for account in accounts:
            if account_id and account.id != account_id:
                continue
            orders = await self.order_repo.get_by_account(account.id, limit=limit)
            all_orders.extend(orders)

        if symbol:
            all_orders = [o for o in all_orders if o.symbol == symbol.upper()]

        all_orders.sort(key=lambda x: x.created_at, reverse=True)
        return all_orders[:limit]

    async def get_open_positions(
        self, user_id: int, account_id: int | None = None
    ) -> list[Position]:
        """获取持仓"""
        accounts = await self.account_repo.get_active_by_user(user_id)
        if not accounts:
            return []

        all_positions = []
        for account in accounts:
            if account_id and account.id != account_id:
                continue
            positions = await self.position_repo.get_open_by_account(account.id)
            all_positions.extend(positions)

        return all_positions

    async def close_position(self, position_id: int, user_id: int) -> Position:
        """平仓"""
        position = await self.position_repo.get_by_id(position_id)
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="持仓不存在",
            )

        account = await self.account_repo.get_by_id(position.account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作",
            )

        if position.status != "open":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="持仓已平仓",
            )

        side = "sell" if position.side == "long" else "buy"
        await self.create_order(
            user_id=user_id,
            account_id=position.account_id,
            symbol=position.symbol,
            side=side,
            order_type="market",
            quantity=position.quantity,
            strategy_instance_id=position.strategy_instance_id,
        )

        position.status = "closed"
        position.closed_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(position)
        return position

    async def emergency_close_all(self, user_id: int, account_id: int | None = None):
        """紧急一键平仓（风控核心功能）"""
        accounts = await self.account_repo.get_active_by_user(user_id)
        closed_positions = []

        for account in accounts:
            if account_id and account.id != account_id:
                continue
            positions = await self.position_repo.get_open_by_account(account.id)
            for position in positions:
                await self.close_position(position.id, user_id)
                closed_positions.append(position)

        return closed_positions

    async def set_stop_loss(
        self, position_id: int, user_id: int, stop_price: Decimal
    ) -> Position:
        """设置止损价格"""
        position = await self.position_repo.get_by_id(position_id)
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="持仓不存在",
            )

        account = await self.account_repo.get_by_id(position.account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作",
            )

        if position.status != "open":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="持仓已平仓",
            )

        # 验证止损价格合理性
        if position.side == "long" and stop_price >= position.entry_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="多头止损价必须低于开仓价",
            )
        if position.side == "short" and stop_price <= position.entry_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="空头止损价必须高于开仓价",
            )

        position.stop_loss_price = stop_price
        await self.session.commit()
        await self.session.refresh(position)
        return position

    async def set_take_profit(
        self, position_id: int, user_id: int, tp_price: Decimal
    ) -> Position:
        """设置止盈价格"""
        position = await self.position_repo.get_by_id(position_id)
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="持仓不存在",
            )

        account = await self.account_repo.get_by_id(position.account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作",
            )

        if position.status != "open":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="持仓已平仓",
            )

        # 验证止盈价格合理性
        if position.side == "long" and tp_price <= position.entry_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="多头止盈价必须高于开仓价",
            )
        if position.side == "short" and tp_price >= position.entry_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="空头止盈价必须低于开仓价",
            )

        position.take_profit_price = tp_price
        await self.session.commit()
        await self.session.refresh(position)
        return position
