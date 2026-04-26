"""
策略服务
"""
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.user import User
from app.models.strategy import StrategyInstance, StrategyTemplate
from app.repositories.strategy_repo import (
    StrategyTemplateRepository,
    StrategyInstanceRepository,
)
from app.api.deps import get_current_user


class StrategyService:
    """策略服务"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.template_repo = StrategyTemplateRepository(session)
        self.instance_repo = StrategyInstanceRepository(session)

    async def get_templates(self) -> list[StrategyTemplate]:
        """获取所有策略模板"""
        return await self.template_repo.get_active_templates()

    async def get_template(self, template_id: int) -> StrategyTemplate | None:
        """获取策略模板详情"""
        return await self.template_repo.get_by_id(template_id)

    async def get_template_by_code(self, code: str) -> StrategyTemplate | None:
        """根据代码获取策略模板"""
        return await self.template_repo.get_by_code(code)

    async def _ensure_template(self, template_id: int | str) -> StrategyTemplate | None:
        """确保策略模板在 DB 中存在，不存在则自动从 seed_data 补建

        Args:
            template_id: 模板ID（int=数据库ID, str=code如ma_cross）
        """
        from app.seed_data import STRATEGY_TEMPLATES

        # 确定要查找的 code
        if isinstance(template_id, int):
            from app.constants import TEMPLATE_ID_TO_CODE
            code = TEMPLATE_ID_TO_CODE.get(template_id)
            if not code:
                return None
        else:
            code = template_id

        # 在 seed_data 中找到对应定义
        seed = next((t for t in STRATEGY_TEMPLATES if t["code"] == code), None)
        if not seed:
            return None

        # 先查一下是否已有（并发安全）
        existing = await self.template_repo.get_by_code(code)
        if existing:
            return existing

        # 创建模板记录
        new_template = StrategyTemplate(
            code=seed["code"],
            name=seed["name"],
            description=seed["description"],
            strategy_type=seed["strategy_type"],
            risk_level=seed.get("risk_level", "medium"),
            params_schema=seed.get("params_schema", {}),
            is_active=True,
        )
        self.session.add(new_template)
        await self.session.flush()
        await self.session.refresh(new_template)
        return new_template

    async def get_user_instances(
        self, user_id: int, active_only: bool = False
    ) -> list[StrategyInstance]:
        """获取用户的策略实例"""
        if active_only:
            return await self.instance_repo.get_active_by_user(user_id)
        return await self.instance_repo.get_by_user(user_id)

    async def get_instance(self, instance_id: int) -> StrategyInstance | None:
        """获取策略实例详情"""
        return await self.instance_repo.get_with_template(instance_id)

    async def create_instance(
        self,
        user: User,
        template_id: int | str,
        name: str,
        symbol: str,
        exchange: str,
        params: dict,
        risk_params: dict,
        direction: str = "both",
        account_id: int | None = None,
    ) -> StrategyInstance:
        """创建策略实例

        Args:
            template_id: 模板ID（可以是int或字符串code）
            account_id: 绑定的交易所账户ID，自动下单时使用
        """
        # 解析模板ID（支持int或字符串）
        template: StrategyTemplate | None = None
        if isinstance(template_id, str):
            template = await self.template_repo.get_by_code(template_id)
        else:
            template = await self.template_repo.get_by_id(template_id)

        # 模板不在DB中时，自动从 seed_data 补建
        if not template:
            template = await self._ensure_template(template_id)
            if not template:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="策略模板不存在",
                )

        # 验证 account_id（如果指定）
        if account_id:
            from app.models.exchange import ExchangeAccount
            from sqlalchemy import select
            result = await self.session.execute(
                select(ExchangeAccount).where(
                    ExchangeAccount.id == account_id,
                    ExchangeAccount.user_id == user.id,
                    ExchangeAccount.is_active == True,
                )
            )
            account = result.scalar_one_or_none()
            if not account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="交易所账户不存在或不可用",
                )

        # 创建实例
        instance = StrategyInstance(
            user_id=user.id,
            template_id=template.id,
            name=name,
            symbol=symbol.upper(),
            exchange=exchange.lower(),
            direction=direction,
            params=params,
            risk_params=risk_params,
            account_id=account_id,
            status="stopped",  # P2-7: 创建后不自动运行，需用户显式启动
        )
        return await self.instance_repo.create(instance)

    async def update_instance(
        self,
        instance_id: int,
        user_id: int,
        **updates,
    ) -> StrategyInstance | None:
        """更新策略实例"""
        instance = await self.instance_repo.get_by_id(instance_id)
        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="策略实例不存在",
            )
        if instance.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作此策略",
            )

        # 更新字段
        allowed_fields = ["name", "symbol", "params", "risk_params", "direction", "account_id"]
        update_dict = {k: v for k, v in updates.items() if k in allowed_fields}

        return await self.instance_repo.update(instance_id, **update_dict)

    async def start_instance(self, instance_id: int, user_id: int) -> StrategyInstance | None:
        """启动策略"""
        instance = await self.instance_repo.get_with_template(instance_id)
        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="策略实例不存在",
            )
        if instance.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作此策略",
            )
        if instance.status == "running":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="策略已在运行",
            )

        instance = await self.instance_repo.update(instance_id, status="running")

        # 启动策略运行器
        try:
            from app.core.strategy_runner import strategy_runner
            await strategy_runner.start_instance(instance_id)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("启动策略运行器失败: %s", exc)

        return instance

    async def stop_instance(self, instance_id: int, user_id: int) -> StrategyInstance | None:
        """停止策略"""
        instance = await self.instance_repo.get_by_id(instance_id)
        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="策略实例不存在",
            )
        if instance.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作此策略",
            )
        if instance.status != "running":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="策略未在运行",
            )

        # 先停止策略运行器
        try:
            from app.core.strategy_runner import strategy_runner
            await strategy_runner.stop_instance(instance_id)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("停止策略运行器失败: %s", exc)

        return await self.instance_repo.update(instance_id, status="stopped")

    async def delete_instance(self, instance_id: int, user_id: int) -> bool:
        """删除策略实例"""
        instance = await self.instance_repo.get_by_id(instance_id)
        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="策略实例不存在",
            )
        if instance.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作此策略",
            )
        if instance.status == "running":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请先停止策略后再删除",
            )

        return await self.instance_repo.delete(instance_id)
