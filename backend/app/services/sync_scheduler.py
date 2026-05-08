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

        # 1. 同步余额（适配器返回 list[Balance]，与 OrderService 一致）
        try:
            balances = await adapter.get_balance()
            if balances:
                for b in balances:
                    if b.asset.upper() == "USDT":
                        account.balance = b.free
                        account.frozen_balance = b.locked
                        break
                else:
                    account.balance = balances[0].free
                    account.frozen_balance = balances[0].locked
                account.last_sync_at = datetime.now(UTC)
                logger.debug(
                    "[SyncScheduler] 账户 #%d 余额同步: free=%s, frozen=%s",
                    account.id,
                    account.balance,
                    account.frozen_balance,
                )
        except Exception as exc:
            logger.warning("[SyncScheduler] 账户 #%d 余额同步失败: %s", account.id, exc)

        # 2. 同步持仓（适配器返回 list[PositionInfo]）
        try:
            from decimal import Decimal

            from sqlalchemy import select

            from app.models.exchange import Position

            exchange_positions = await adapter.get_positions()
            if exchange_positions:
                for ep in exchange_positions:
                    symbol = ep.symbol
                    side = ep.side
                    quantity = ep.quantity
                    entry_price = ep.entry_price
                    current_price = ep.current_price

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
                        position.leverage = ep.leverage or position.leverage
                        position.unrealized_pnl = ep.unrealized_pnl
                        if entry_price and entry_price > 0:
                            position.unrealized_pnl_percent = (
                                ep.unrealized_pnl / (entry_price * quantity) * Decimal("100")
                            )
                    else:
                        upnl_pct = Decimal("0")
                        if entry_price and entry_price > 0:
                            upnl_pct = ep.unrealized_pnl / (entry_price * quantity) * Decimal("100")
                        new_pos = Position(
                            account_id=account.id,
                            symbol=symbol,
                            side=side,
                            quantity=quantity,
                            entry_price=entry_price,
                            current_price=current_price,
                            leverage=ep.leverage or 1,
                            unrealized_pnl=ep.unrealized_pnl,
                            unrealized_pnl_percent=upnl_pct,
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
