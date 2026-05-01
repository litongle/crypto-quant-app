"""
订单状态对账服务 - P0-3

定时查询交易所未完成订单状态，同步到本地数据库。
- 成交 → 更新 status=filled + avg_fill_price + commission + pnl
- 取消 → 更新 status=cancelled
- 拒绝 → 更新 status=rejected
- 部分成交 → 更新 status=partial
"""
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exchange import ExchangeAccount
from app.models.order import Order
from app.repositories.trading_repo import ExchangeAccountRepository, OrderRepository

logger = logging.getLogger(__name__)

# 对账轮询间隔（秒）
_RECONCILE_INTERVAL = 45


class OrderReconciliationService:
    """订单状态对账服务"""

    def __init__(self, session_maker):
        self._session_maker = session_maker
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """启动对账服务"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._reconcile_loop(),
            name="order-reconciliation",
        )
        logger.info("[OrderReconciliation] 启动，轮询间隔 %d 秒", _RECONCILE_INTERVAL)

    async def stop(self) -> None:
        """停止对账服务"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("[OrderReconciliation] 已停止")

    async def _reconcile_loop(self) -> None:
        """对账主循环"""
        while self._running:
            try:
                await self._reconcile_once()
            except Exception as exc:
                logger.error("[OrderReconciliation] 对账异常: %s", exc)
            await asyncio.sleep(_RECONCILE_INTERVAL)

    async def _reconcile_once(self) -> None:
        """执行一次对账"""
        async with self._session_maker() as session:
            # 获取所有需要同步的订单（submitted 或 partial 状态）
            order_repo = OrderRepository(session)
            account_repo = ExchangeAccountRepository(session)

            # 查询所有未完成的订单
            result = await session.execute(
                select(Order).where(
                    Order.status.in_(["submitted", "partial"])
                )
            )
            pending_orders = result.scalars().all()

            if not pending_orders:
                return

            logger.debug("[OrderReconciliation] 开始对账，%d 个未完成订单", len(pending_orders))

            # 按账户分组，减少 API 调用
            orders_by_account: dict[int, list[Order]] = {}
            for order in pending_orders:
                orders_by_account.setdefault(order.account_id, []).append(order)

            for account_id, orders in orders_by_account.items():
                try:
                    account = await account_repo.get_by_id(account_id)
                    if not account or not account.is_active:
                        continue

                    await self._sync_account_orders(session, account, orders)
                except Exception as exc:
                    logger.error(
                        "[OrderReconciliation] 账户 #%d 对账失败: %s",
                        account_id, exc,
                    )

            await session.commit()

    async def _sync_account_orders(
        self,
        session: AsyncSession,
        account: ExchangeAccount,
        orders: list[Order],
    ) -> None:
        """同步单个账户的订单状态"""
        from app.core.exchange_adapter import get_exchange_adapter

        adapter = get_exchange_adapter(
            exchange=account.exchange,
            api_key=account.get_api_key(),
            secret_key=account.get_secret_key(),
            passphrase=account.get_passphrase() if account.encrypted_passphrase else None,
            testnet=account.is_testnet,
            is_demo=account.is_demo,
        )

        for order in orders:
            if not order.exchange_order_id:
                continue

            try:
                # 查询交易所订单状态
                exchange_order = await adapter.get_order_status(
                    order.exchange_order_id, order.symbol
                )

                if not exchange_order:
                    logger.warning(
                        "[OrderReconciliation] 订单 #%d 在交易所不存在: exchange_order_id=%s",
                        order.id, order.exchange_order_id,
                    )
                    continue

                # 更新本地订单状态
                old_status = order.status
                new_status = exchange_order.status

                # 状态映射
                status_map = {
                    "filled": "filled",
                    "canceled": "cancelled",
                    "cancelled": "cancelled",
                    "rejected": "rejected",
                    "expired": "cancelled",
                    "partial": "partial",
                }
                mapped_status = status_map.get(new_status, new_status)

                if mapped_status != old_status:
                    order.status = mapped_status
                    logger.info(
                        "[OrderReconciliation] 订单 #%d 状态更新: %s → %s",
                        order.id, old_status, mapped_status,
                    )

                # 更新成交信息
                if exchange_order.filled_quantity and exchange_order.filled_quantity > 0:
                    order.filled_quantity = exchange_order.filled_quantity
                if exchange_order.avg_fill_price and exchange_order.avg_fill_price > 0:
                    order.avg_fill_price = exchange_order.avg_fill_price
                if exchange_order.commission and exchange_order.commission > 0:
                    order.commission = exchange_order.commission

                # 计算订单价值
                if order.avg_fill_price and order.filled_quantity:
                    order.order_value = order.avg_fill_price * order.filled_quantity

                # 成交时间
                if mapped_status == "filled" and not order.filled_at:
                    order.filled_at = datetime.now(timezone.utc)

                # 计算已实现盈亏（如果是平仓订单）
                if mapped_status == "filled" and order.strategy_instance_id:
                    await self._calculate_realized_pnl(session, order)

            except Exception as exc:
                logger.warning(
                    "[OrderReconciliation] 订单 #%d 同步失败: %s",
                    order.id, exc,
                )

    async def _calculate_realized_pnl(self, session: AsyncSession, order: Order) -> None:
        """计算订单的已实现盈亏"""
        try:
            from app.models.exchange import Position

            # 查找关联的持仓
            result = await session.execute(
                select(Position).where(
                    Position.account_id == order.account_id,
                    Position.symbol == order.symbol,
                    Position.status == "open",
                )
            )
            position = result.scalar_one_or_none()

            if position and order.avg_fill_price and position.entry_price:
                if position.side == "long" and order.side == "sell":
                    # 平多
                    order.pnl = (order.avg_fill_price - position.entry_price) * order.filled_quantity
                elif position.side == "short" and order.side == "buy":
                    # 平空
                    order.pnl = (position.entry_price - order.avg_fill_price) * order.filled_quantity

                # 扣除手续费
                if order.pnl and order.commission:
                    order.pnl -= order.commission

        except Exception as exc:
            logger.debug("[OrderReconciliation] 计算盈亏失败: %s", exc)


# 全局单例
_reconciliation_service: OrderReconciliationService | None = None


async def start_reconciliation(session_maker) -> OrderReconciliationService:
    """启动对账服务"""
    global _reconciliation_service
    if _reconciliation_service is None:
        _reconciliation_service = OrderReconciliationService(session_maker)
        await _reconciliation_service.start()
    return _reconciliation_service


async def stop_reconciliation() -> None:
    """停止对账服务"""
    global _reconciliation_service
    if _reconciliation_service:
        await _reconciliation_service.stop()
        _reconciliation_service = None
