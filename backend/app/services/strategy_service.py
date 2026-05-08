"""
策略服务
"""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.strategy import StrategyInstance, StrategyTemplate
from app.models.user import User
from app.repositories.strategy_repo import (
    StrategyInstanceRepository,
    StrategyTemplateRepository,
)

MAX_INSTANCES_PER_USER = 20
LIVE_TRADING_TEMPLATE_CODES = frozenset(
    {
        "ma_cross",
        "rsi",
        "bollinger",
        "grid",
        "martingale",
        "rule_custom",
        "rsi_layered",
        "dca",
    }
)


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

    async def _ensure_instance_quota(self, user_id: int) -> None:
        """校验用户策略实例数量上限"""
        current_count = await self.instance_repo.count_by_user(user_id)
        if current_count >= MAX_INSTANCES_PER_USER:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"策略实例数量已达上限 ({MAX_INSTANCES_PER_USER}个)，请删除后再创建",
            )

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
        await self._ensure_instance_quota(user.id)

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

        self._validate_live_trading_settings(
            template_code=template.code,
            account_id=account_id,
            params=params,
        )

        # 验证 account_id（如果指定）
        if account_id:
            from sqlalchemy import select

            from app.models.exchange import ExchangeAccount

            result = await self.session.execute(
                select(ExchangeAccount).where(
                    ExchangeAccount.id == account_id,
                    ExchangeAccount.user_id == user.id,
                    ExchangeAccount.is_active,
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
            status="draft",
            workspace_state="library",
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
        if instance.workspace_state != "draft":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="正式策略不能直接编辑，请先复制为工作台草案",
            )

        if "account_id" in updates:
            account_id = updates["account_id"]
            if account_id:
                from sqlalchemy import select

                from app.models.exchange import ExchangeAccount

                result = await self.session.execute(
                    select(ExchangeAccount).where(
                        ExchangeAccount.id == account_id,
                        ExchangeAccount.user_id == user_id,
                        ExchangeAccount.is_active,
                    )
                )
                account = result.scalar_one_or_none()
                if not account:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="交易所账户不存在或不可用",
                    )

        if "workspace_state" in updates and updates["workspace_state"] == "running":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能通过编辑直接把策略放入运行台，请使用启动操作",
            )

        template = await self.get_template(instance.template_id)
        if template:
            next_params = updates.get("params", instance.params or {})
            next_account_id = updates.get("account_id", instance.account_id)
            self._validate_live_trading_settings(
                template_code=template.code,
                account_id=next_account_id,
                params=next_params,
            )

        allowed_fields = [
            "name",
            "exchange",
            "symbol",
            "account_id",
            "params",
            "risk_params",
            "direction",
            "workspace_state",
        ]
        update_dict = {k: v for k, v in updates.items() if k in allowed_fields}
        if "symbol" in update_dict and update_dict["symbol"]:
            update_dict["symbol"] = str(update_dict["symbol"]).upper()
        if "exchange" in update_dict and update_dict["exchange"]:
            update_dict["exchange"] = str(update_dict["exchange"]).lower()

        return await self.instance_repo.update(instance_id, **update_dict)

    async def start_instance(self, instance_id: int, user_id: int) -> StrategyInstance | None:
        """启动策略（带数据库级并发锁）"""
        instance = await self.instance_repo.get_with_template_for_update(instance_id)
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

        template_code = instance.template.code if instance.template else None
        auto_trade_enabled = bool((instance.params or {}).get("auto_trade"))
        self._validate_live_trading_settings(
            template_code=template_code,
            account_id=instance.account_id,
            params=instance.params or {},
        )
        if auto_trade_enabled and not instance.account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="开启自动下单前请先绑定交易所账户",
            )
        try:
            from app.core.strategy_runner import strategy_runner

            runtime_status = strategy_runner.get_status(instance_id)
            runtime_active = bool(runtime_status.get("runtime_active"))
            if instance.status == "running" and runtime_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="策略已在运行",
                )

            started = await strategy_runner.start_instance(instance_id)
            if not started:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="策略启动失败，请稍后重试",
                )
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            import logging

            logging.getLogger(__name__).warning("启动策略运行器失败: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="策略运行器暂时不可用，请稍后重试",
            ) from exc

        now = datetime.now(UTC)
        try:
            instance = await self.instance_repo.update(
                instance_id,
                status="running",
                workspace_state="running",
                last_started_at=now,
                last_run_at=now,
            )
        except Exception:
            try:
                from app.core.strategy_runner import strategy_runner

                await strategy_runner.stop_instance(instance_id)
            except Exception:
                pass
            raise

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

        try:
            from app.core.strategy_runner import strategy_runner

            await strategy_runner.stop_instance(instance_id)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("停止策略运行器失败: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="策略停止失败，请稍后重试",
            ) from exc

        return await self.instance_repo.update(
            instance_id,
            status="stopped",
            workspace_state="library",
            last_stopped_at=datetime.now(UTC),
        )

    async def clone_to_draft(self, instance_id: int, user_id: int) -> StrategyInstance:
        """复制策略为工作台草案"""
        instance = await self.instance_repo.get_with_template_for_update(instance_id)
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
        if instance.workspace_state == "draft":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="工作台草案已可直接编辑，无需再次复制",
            )
        existing_draft = await self.instance_repo.get_existing_draft_by_source(user_id, instance.id)
        if existing_draft:
            return existing_draft

        await self._ensure_instance_quota(user_id)
        return await self.instance_repo.clone_to_draft(instance)

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

        await self.instance_repo.clear_source_references(instance_id)
        return await self.instance_repo.delete(instance_id)

    def _validate_live_trading_settings(
        self,
        *,
        template_code: str | None,
        account_id: int | None,
        params: dict | None,
    ) -> None:
        """校验模板是否允许进入真实下单配置。"""
        code = str(template_code or "")
        if not code:
            return

        auto_trade_enabled = bool((params or {}).get("auto_trade"))
        if code in LIVE_TRADING_TEMPLATE_CODES:
            return

        if account_id or auto_trade_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"策略模板 {code} 暂不支持真实自动下单",
            )
