"""
策略仓储
"""

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.strategy import StrategyInstance, StrategyTemplate
from app.repositories.base import BaseRepository


class StrategyTemplateRepository(BaseRepository[StrategyTemplate]):
    """策略模板仓储"""

    def __init__(self, session: AsyncSession):
        super().__init__(StrategyTemplate, session)

    async def get_active_templates(self) -> list[StrategyTemplate]:
        """获取所有活跃模板"""
        result = await self.session.execute(
            select(StrategyTemplate).where(StrategyTemplate.is_active)
        )
        return list(result.scalars().all())

    async def get_by_type(self, strategy_type: str) -> StrategyTemplate | None:
        """根据类型获取模板"""
        result = await self.session.execute(
            select(StrategyTemplate).where(
                StrategyTemplate.strategy_type == strategy_type,
                StrategyTemplate.is_active,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> StrategyTemplate | None:
        """根据代码获取模板"""
        result = await self.session.execute(
            select(StrategyTemplate).where(
                StrategyTemplate.code == code,
                StrategyTemplate.is_active,
            )
        )
        return result.scalar_one_or_none()


class StrategyInstanceRepository(BaseRepository[StrategyInstance]):
    """策略实例仓储"""

    DRAFT_NAME_SUFFIX = " (草稿)"
    MAX_NAME_LENGTH = 100

    def __init__(self, session: AsyncSession):
        super().__init__(StrategyInstance, session)

    async def get_by_user(self, user_id: int) -> list[StrategyInstance]:
        """获取用户的所有策略实例"""
        result = await self.session.execute(
            select(StrategyInstance)
            .where(StrategyInstance.user_id == user_id)
            .options(selectinload(StrategyInstance.template))
            .order_by(
                case(
                    (StrategyInstance.workspace_state == "running", 0),
                    (StrategyInstance.workspace_state == "library", 1),
                    else_=2,
                ),
                StrategyInstance.updated_at.desc(),
                StrategyInstance.id.desc(),
            )
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

    async def count_by_user(self, user_id: int) -> int:
        """统计用户策略实例数量"""
        result = await self.session.execute(
            select(func.count(StrategyInstance.id)).where(StrategyInstance.user_id == user_id)
        )
        return result.scalar_one() or 0

    async def get_by_user_and_symbol(self, user_id: int, symbol: str) -> list[StrategyInstance]:
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
            .options(
                selectinload(StrategyInstance.template),
                selectinload(StrategyInstance.source_instance),
            )
        )
        return result.scalar_one_or_none()

    async def get_with_template_for_update(self, instance_id: int) -> StrategyInstance | None:
        """获取策略实例（含模板），加行级锁防止并发启动"""
        result = await self.session.execute(
            select(StrategyInstance)
            .where(StrategyInstance.id == instance_id)
            .options(
                selectinload(StrategyInstance.template),
                selectinload(StrategyInstance.source_instance),
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def clear_source_references(self, instance_id: int) -> None:
        """删除原策略前清理其草稿副本对 source_instance_id 的引用"""
        await self.session.execute(
            update(StrategyInstance)
            .where(StrategyInstance.source_instance_id == instance_id)
            .values(source_instance_id=None)
        )
        await self.session.flush()

    async def get_existing_draft_by_source(
        self,
        user_id: int,
        source_instance_id: int,
    ) -> StrategyInstance | None:
        """查找来源策略已有的工作台草案，避免重复复制"""
        result = await self.session.execute(
            select(StrategyInstance)
            .options(
                selectinload(StrategyInstance.template),
                selectinload(StrategyInstance.source_instance),
            )
            .where(
                StrategyInstance.user_id == user_id,
                StrategyInstance.source_instance_id == source_instance_id,
                StrategyInstance.workspace_state == "draft",
            )
            .order_by(StrategyInstance.updated_at.desc(), StrategyInstance.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def build_draft_name(self, name: str) -> str:
        """生成不超过字段长度上限的草稿名称"""
        base_name = (name or "").strip() or "未命名策略"
        remaining = self.MAX_NAME_LENGTH - len(self.DRAFT_NAME_SUFFIX)
        if remaining <= 0:
            return self.DRAFT_NAME_SUFFIX[: self.MAX_NAME_LENGTH]
        return f"{base_name[:remaining]}{self.DRAFT_NAME_SUFFIX}"

    async def clone_to_draft(self, instance: StrategyInstance) -> StrategyInstance:
        """复制策略为工作台草案"""
        draft = StrategyInstance(
            user_id=instance.user_id,
            template_id=instance.template_id,
            account_id=instance.account_id,
            name=self.build_draft_name(instance.name),
            symbol=instance.symbol,
            exchange=instance.exchange,
            direction=instance.direction,
            params=dict(instance.params or {}),
            risk_params=dict(instance.risk_params or {}),
            status="draft",
            workspace_state="draft",
            source_instance_id=instance.id,
        )
        return await self.create(draft)
