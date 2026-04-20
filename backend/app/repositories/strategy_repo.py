"""
策略仓储
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.strategy import StrategyTemplate, StrategyInstance
from app.repositories.base import BaseRepository


class StrategyTemplateRepository(BaseRepository[StrategyTemplate]):
    """策略模板仓储"""

    def __init__(self, session: AsyncSession):
        super().__init__(StrategyTemplate, session)

    async def get_active_templates(self) -> list[StrategyTemplate]:
        """获取所有活跃模板"""
        result = await self.session.execute(
            select(StrategyTemplate).where(StrategyTemplate.is_active == True)
        )
        return list(result.scalars().all())

    async def get_by_type(self, strategy_type: str) -> StrategyTemplate | None:
        """根据类型获取模板"""
        result = await self.session.execute(
            select(StrategyTemplate).where(
                StrategyTemplate.strategy_type == strategy_type,
                StrategyTemplate.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> StrategyTemplate | None:
        """根据代码获取模板"""
        result = await self.session.execute(
            select(StrategyTemplate).where(
                StrategyTemplate.code == code,
                StrategyTemplate.is_active == True,
            )
        )
        return result.scalar_one_or_none()


class StrategyInstanceRepository(BaseRepository[StrategyInstance]):
    """策略实例仓储"""

    def __init__(self, session: AsyncSession):
        super().__init__(StrategyInstance, session)

    async def get_by_user(self, user_id: int) -> list[StrategyInstance]:
        """获取用户的所有策略实例"""
        result = await self.session.execute(
            select(StrategyInstance)
            .where(StrategyInstance.user_id == user_id)
            .options(selectinload(StrategyInstance.template))
        )
        return list(result.scalars().all())

    async def get_active_by_user(self, user_id: int) -> list[StrategyInstance]:
        """获取用户活跃的策略实例"""
        result = await self.session.execute(
            select(StrategyInstance)
            .where(
                StrategyInstance.user_id == user_id,
                StrategyInstance.status == "running",  # 使用 running 状态
            )
            .options(selectinload(StrategyInstance.template))
        )
        return list(result.scalars().all())

    async def get_by_user_and_symbol(
        self, user_id: int, symbol: str
    ) -> list[StrategyInstance]:
        """获取用户在指定交易对上的策略"""
        result = await self.session.execute(
            select(StrategyInstance).where(
                StrategyInstance.user_id == user_id,
                StrategyInstance.symbol == symbol,
            )
        )
        return list(result.scalars().all())

    async def get_with_template(self, instance_id: int) -> StrategyInstance | None:
        """获取策略实例（含模板）"""
        result = await self.session.execute(
            select(StrategyInstance)
            .where(StrategyInstance.id == instance_id)
            .options(selectinload(StrategyInstance.template))
        )
        return result.scalar_one_or_none()
