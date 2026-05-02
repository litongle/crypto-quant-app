"""
定时同步调度服务 - P1-4

FastAPI lifespan 内启动 asyncio.Task，每 5 分钟自动同步：
- 交易所账户余额
- 持仓数据
- 订单状态
"""

import asyncio
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

_SYNC_INTERVAL = 300  # 5 分钟


class SyncScheduler:
    """定时同步调度器"""

    def __init__(self, session_maker):
        self._session_maker = session_maker
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._sync_loop(), name="sync-scheduler")
        logger.info("[SyncScheduler] 启动，同步间隔 %d 秒", _SYNC_INTERVAL)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("[SyncScheduler] 已停止")

    async def _sync_loop(self) -> None:
        while self._running:
            try:
                await self._sync_all()
            except Exception as exc:
                logger.error("[SyncScheduler] 同步异常: %s", exc)
            await asyncio.sleep(_SYNC_INTERVAL)

    async def _sync_all(self) -> None:
        """执行全量同步"""
        async with self._session_maker() as session:
            from sqlalchemy import select

            from app.models.exchange import ExchangeAccount

            result = await session.execute(
                select(ExchangeAccount).where(
                    ExchangeAccount.is_active,
                    ExchangeAccount.status == "active",
                )
            )
            accounts = result.scalars().all()

            if not accounts:
                return

            logger.info("[SyncScheduler] 开始同步 %d 个账户", len(accounts))

            for account in accounts:
                try:
                    await self._sync_account(session, account)
                except Exception as exc:
                    logger.error(
                        "[SyncScheduler] 账户 #%d (%s) 同步失败: %s",
                        account.id,
                        account.account_name,
                        exc,
                    )

            await session.commit()

    async def _sync_account(self, session, account) -> None:
        """同步单个账户的余额和持仓"""
        from app.core.exchange_adapter import get_exchange_adapter

        adapter = get_exchange_adapter(
            exchange=account.exchange,
            api_key=account.get_api_key(),
            secret_key=account.get_secret_key(),
            passphrase=account.get_passphrase() if account.encrypted_passphrase else None,
            testnet=account.is_testnet,
            is_demo=account.is_demo,
        )

        # 1. 同步余额
        try:
            balance_info = await adapter.get_balance()
            if balance_info:
                account.balance = balance_info.get("free", account.balance)
                account.frozen_balance = balance_info.get("frozen", account.frozen_balance)
                account.last_sync_at = datetime.now(UTC)
                logger.debug(
                    "[SyncScheduler] 账户 #%d 余额同步: free=%s, frozen=%s",
                    account.id,
                    account.balance,
                    account.frozen_balance,
                )
        except Exception as exc:
            logger.warning("[SyncScheduler] 账户 #%d 余额同步失败: %s", account.id, exc)

        # 2. 同步持仓
        try:
            from decimal import Decimal

            from sqlalchemy import select

            from app.models.exchange import Position

            exchange_positions = await adapter.get_positions()
            if exchange_positions:
                for ep in exchange_positions:
                    symbol = ep.get("symbol", "")
                    side = ep.get("side", "long")
                    quantity = Decimal(str(ep.get("quantity", 0)))
                    entry_price = Decimal(str(ep.get("entry_price", 0)))
                    current_price = Decimal(str(ep.get("current_price", entry_price)))

                    if quantity <= 0:
                        continue

                    # 查找是否已有该持仓
                    pos_result = await session.execute(
                        select(Position).where(
                            Position.account_id == account.id,
                            Position.symbol == symbol,
                            Position.side == side,
                            Position.status == "open",
                        )
                    )
                    position = pos_result.scalar_one_or_none()

                    if position:
                        position.quantity = quantity
                        position.entry_price = entry_price
                        position.current_price = current_price
                        if entry_price and entry_price > 0:
                            if side == "long":
                                position.unrealized_pnl = (current_price - entry_price) * quantity
                            else:
                                position.unrealized_pnl = (entry_price - current_price) * quantity
                            position.unrealized_pnl_percent = (
                                position.unrealized_pnl / (entry_price * quantity) * 100
                            )
                    else:
                        new_pos = Position(
                            account_id=account.id,
                            symbol=symbol,
                            side=side,
                            quantity=quantity,
                            entry_price=entry_price,
                            current_price=current_price,
                            status="open",
                        )
                        session.add(new_pos)

                logger.debug(
                    "[SyncScheduler] 账户 #%d 持仓同步: %d 个",
                    account.id,
                    len(exchange_positions),
                )
        except Exception as exc:
            logger.warning("[SyncScheduler] 账户 #%d 持仓同步失败: %s", account.id, exc)


# 全局单例
_sync_scheduler: SyncScheduler | None = None


async def start_sync_scheduler(session_maker) -> SyncScheduler:
    global _sync_scheduler
    if _sync_scheduler is None:
        _sync_scheduler = SyncScheduler(session_maker)
        await _sync_scheduler.start()
    return _sync_scheduler


async def stop_sync_scheduler() -> None:
    global _sync_scheduler
    if _sync_scheduler:
        await _sync_scheduler.stop()
        _sync_scheduler = None
