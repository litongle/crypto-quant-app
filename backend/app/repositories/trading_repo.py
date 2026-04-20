"""
交易相关仓储
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.exchange import ExchangeAccount, Position
from app.models.order import Order, Signal
from app.repositories.base import BaseRepository


class ExchangeAccountRepository(BaseRepository[ExchangeAccount]):
    """交易所账户仓储"""

    def __init__(self, session: AsyncSession):
        super().__init__(ExchangeAccount, session)

    async def get_by_user(self, user_id: int) -> list[ExchangeAccount]:
        """获取用户的所有交易所账户"""
        result = await self.session.execute(
            select(ExchangeAccount).where(ExchangeAccount.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_active_by_user(self, user_id: int) -> list[ExchangeAccount]:
        """获取用户活跃的交易所账户"""
        result = await self.session.execute(
            select(ExchangeAccount).where(
                ExchangeAccount.user_id == user_id,
                ExchangeAccount.is_active == True,
            )
        )
        return list(result.scalars().all())

    async def get_by_user_and_exchange(
        self, user_id: int, exchange: str
    ) -> ExchangeAccount | None:
        """获取用户在指定交易所的账户"""
        result = await self.session.execute(
            select(ExchangeAccount).where(
                ExchangeAccount.user_id == user_id,
                ExchangeAccount.exchange == exchange,
            )
        )
        return result.scalar_one_or_none()


class PositionRepository(BaseRepository[Position]):
    """持仓仓储"""

    def __init__(self, session: AsyncSession):
        super().__init__(Position, session)

    async def get_open_by_account(self, account_id: int) -> list[Position]:
        """获取账户的持仓"""
        result = await self.session.execute(
            select(Position).where(
                Position.account_id == account_id,
                Position.status == "open",
            )
        )
        return list(result.scalars().all())

    async def get_by_account_and_symbol(
        self, account_id: int, symbol: str
    ) -> list[Position]:
        """获取账户在指定交易对的持仓"""
        result = await self.session.execute(
            select(Position).where(
                Position.account_id == account_id,
                Position.symbol == symbol,
                Position.status == "open",
            )
        )
        return list(result.scalars().all())

    async def get_by_strategy(
        self, strategy_instance_id: int, status: str = "open"
    ) -> list[Position]:
        """获取策略的持仓"""
        query = select(Position).where(
            Position.strategy_instance_id == strategy_instance_id
        )
        if status:
            query = query.where(Position.status == status)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_total_exposure(
        self, account_id: int, symbol: str | None = None
    ) -> Decimal:
        """计算总风险敞口"""
        query = select(Position).where(
            Position.account_id == account_id,
            Position.status == "open",
        )
        if symbol:
            query = query.where(Position.symbol == symbol)
        result = await self.session.execute(query)
        positions = result.scalars().all()
        return sum(p.quantity * p.current_price for p in positions)


class OrderRepository(BaseRepository[Order]):
    """订单仓储"""

    def __init__(self, session: AsyncSession):
        super().__init__(Order, session)

    async def get_by_account(
        self,
        account_id: int,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Order]:
        """获取账户的订单"""
        query = select(Order).where(Order.account_id == account_id)
        if status:
            query = query.where(Order.status == status)
        query = query.order_by(Order.created_at.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_strategy(
        self, strategy_instance_id: int, limit: int = 100
    ) -> list[Order]:
        """获取策略的订单"""
        result = await self.session.execute(
            select(Order)
            .where(Order.strategy_instance_id == strategy_instance_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_pending_orders(
        self, account_id: int, symbol: str | None = None
    ) -> list[Order]:
        """获取待成交订单"""
        query = select(Order).where(
            Order.account_id == account_id,
            Order.status.in_(["pending", "submitted", "partial"]),
        )
        if symbol:
            query = query.where(Order.symbol == symbol)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_exchange_order_id(
        self, exchange_order_id: str
    ) -> Order | None:
        """根据交易所订单ID获取"""
        result = await self.session.execute(
            select(Order).where(Order.exchange_order_id == exchange_order_id)
        )
        return result.scalar_one_or_none()


class SignalRepository(BaseRepository[Signal]):
    """信号仓储"""

    def __init__(self, session: AsyncSession):
        super().__init__(Signal, session)

    async def get_pending_by_strategy(
        self, strategy_instance_id: int
    ) -> list[Signal]:
        """获取策略待执行的信号"""
        result = await self.session.execute(
            select(Signal).where(
                Signal.strategy_instance_id == strategy_instance_id,
                Signal.status == "pending",
            )
        )
        return list(result.scalars().all())

    async def get_recent_by_strategy(
        self,
        strategy_instance_id: int,
        hours: int = 24,
        limit: int = 50,
    ) -> list[Signal]:
        """获取策略最近的信号"""
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(hours=hours)
        result = await self.session.execute(
            select(Signal)
            .where(
                Signal.strategy_instance_id == strategy_instance_id,
                Signal.created_at >= cutoff,
            )
            .order_by(Signal.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def expire_old_signals(self, strategy_instance_id: int) -> int:
        """过期过时的信号"""
        from datetime import timedelta

        cutoff = datetime.utcnow()
        result = await self.session.execute(
            select(Signal)
            .where(
                Signal.strategy_instance_id == strategy_instance_id,
                Signal.status == "pending",
                Signal.expires_at < cutoff,
            )
        )
        signals = result.scalars().all()
        for signal in signals:
            signal.status = "expired"
        await self.session.flush()
        return len(signals)
