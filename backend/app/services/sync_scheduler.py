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


_AUTH_FAILURE_KEYWORDS = (
    "ok-access-key",
    "invalid api",
    "api-key",
    "401",
    "403",
    "unauthorized",
    "permission denied",
)


def _is_auth_failure(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(k in text for k in _AUTH_FAILURE_KEYWORDS)


class SyncScheduler:
    """定时同步调度器"""

    def __init__(self, session_maker):
        self._session_maker = session_maker
        self._task: asyncio.Task | None = None
        self._running = False
        # 账户级失败计数 — 连续 N 次失败才告警,避免每 5 分钟一刷
        self._consecutive_failures: dict[int, int] = {}

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

    async def _record_sync_failure(self, account, exc: Exception, *, source: str) -> None:
        """连续失败 3 次以上才记 audit (避免每 5 分钟刷屏); API 凭证错误立即记 critical。"""
        from app.services.audit_service import log_risk_alert

        self._consecutive_failures[account.id] = self._consecutive_failures.get(account.id, 0) + 1
        count = self._consecutive_failures[account.id]
        auth_failure = _is_auth_failure(exc)

        # API 凭证错误立即告警;其他错误连续 3 次才告警
        if not auth_failure and count < 3:
            return

        alert_type = "API 凭证失效" if auth_failure else "余额同步连续失败"
        severity = "critical" if auth_failure else "warning"
        message = (
            f'账户 "{account.account_name}" ({account.exchange}) {source}失败: {str(exc)[:160]}'
        )

        await log_risk_alert(
            self._session_maker,
            alert_type=alert_type,
            message=message,
            severity=severity,
            account_id=account.id,
            metrics={
                "exchange": account.exchange,
                "consecutive_failures": count,
                "trigger": source,
            },
        )

    async def _sync_loop(self) -> None:
        while self._running:
            try:
                await self._sync_all()
            except Exception as exc:
                logger.error("[SyncScheduler] 同步异常: %s", exc)
            await asyncio.sleep(_SYNC_INTERVAL)

    async def _sync_all(self) -> None:
        """执行全量同步 — 跳过 is_paper 账户（本地模拟,余额本地维护,无外部 API）。"""
        async with self._session_maker() as session:
            from sqlalchemy import select

            from app.models.exchange import ExchangeAccount

            result = await session.execute(
                select(ExchangeAccount).where(
                    ExchangeAccount.is_active,
                    ExchangeAccount.status == "active",
                    ExchangeAccount.is_paper.is_(False),
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
            # 同步成功 → 清失败计数
            self._consecutive_failures.pop(account.id, None)
        except Exception as exc:
            logger.warning("[SyncScheduler] 账户 #%d 余额同步失败: %s", account.id, exc)
            await self._record_sync_failure(account, exc, source="定时同步")

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

        # 3. upsert 当天权益快照 — 每 5 分钟覆盖一次，最后一次同步即当日收盘
        try:
            await self._upsert_today_snapshot(session, account)
        except Exception as exc:
            logger.warning("[SyncScheduler] 账户 #%d 权益快照失败: %s", account.id, exc)

    async def _upsert_today_snapshot(self, session, account) -> None:
        """upsert 当天权益快照 (UNIQUE on account_id+snapshot_date)"""
        from decimal import Decimal

        from sqlalchemy import select
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from app.models.equity_snapshot import DailyEquitySnapshot
        from app.models.exchange import Position

        # 计算持仓估值 = sum(qty * current_price + unrealized_pnl)
        # 对永续合约 unrealized_pnl 已经反映了价差；不重复加，只用 (qty * current_price) 表示市值
        # 对现货 unrealized_pnl 不一定 != 0，但 qty * current_price 仍正确
        positions_q = await session.execute(
            select(Position).where(
                Position.account_id == account.id,
                Position.status == "open",
            )
        )
        positions_value = Decimal("0")
        for p in positions_q.scalars():
            if p.current_price and p.quantity:
                positions_value += p.current_price * p.quantity
        balance = account.balance or Decimal("0")
        frozen = account.frozen_balance or Decimal("0")
        total = balance + frozen + positions_value
        today = datetime.now(UTC).date()

        stmt = (
            pg_insert(DailyEquitySnapshot)
            .values(
                account_id=account.id,
                snapshot_date=today,
                balance=balance,
                frozen_balance=frozen,
                positions_value=positions_value,
                total_equity=total,
            )
            .on_conflict_do_update(
                index_elements=["account_id", "snapshot_date"],
                set_={
                    "balance": balance,
                    "frozen_balance": frozen,
                    "positions_value": positions_value,
                    "total_equity": total,
                },
            )
        )
        await session.execute(stmt)


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
