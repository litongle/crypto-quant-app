"""
资产服务 - 资产汇总、权益计算
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.performance import PerformanceCalculator, TradeRecord
from app.models.exchange import Position
from app.models.strategy import StrategyInstance
from app.repositories.strategy_repo import StrategyInstanceRepository
from app.repositories.trading_repo import (
    ExchangeAccountRepository,
    OrderRepository,
    PositionRepository,
)


class AssetService:
    """资产服务"""

    # MNT-04: 提取为命名常量
    DEFAULT_INITIAL_CAPITAL = Decimal("100000")  # 默认初始资金（USDT）

    def __init__(self, session: AsyncSession):
        self.session = session
        self.position_repo = PositionRepository(session)
        self.order_repo = OrderRepository(session)
        self.account_repo = ExchangeAccountRepository(session)
        self.strategy_repo = StrategyInstanceRepository(session)

    async def get_asset_summary(self, user_id: int, exchange: str = "all") -> dict:
        """
        获取资产汇总

        Args:
            user_id: 用户ID
            exchange: 交易所筛选

        Returns:
            dict: 资产汇总数据
        """
        # 获取用户账户
        accounts = await self.account_repo.get_active_by_user(user_id)
        if exchange != "all":
            accounts = [a for a in accounts if a.exchange == exchange]

        total_asset = Decimal("0")
        today_trade_count = 0
        total_pnl = Decimal("0")
        available_balance = Decimal("0")
        locked_balance = Decimal("0")
        today_pnl = Decimal("0")
        initial_capital = self.DEFAULT_INITIAL_CAPITAL

        # PRF-04: 批量加载所有持仓，避免 N+1 查询
        account_ids = [a.id for a in accounts]
        all_positions = []
        if account_ids:
            pos_result = await self.session.execute(
                select(Position).where(
                    Position.account_id.in_(account_ids),
                    Position.status == "open",
                )
            )
            all_positions = list(pos_result.scalars().all())

        # 按账户ID分组持仓
        positions_by_account: dict[int, list[Position]] = {}
        for pos in all_positions:
            positions_by_account.setdefault(pos.account_id, []).append(pos)

        for account in accounts:
            # 账户余额
            total_asset += account.balance
            total_asset += account.frozen_balance

            available_balance += account.balance
            locked_balance += account.frozen_balance

            # 持仓盈亏
            for pos in positions_by_account.get(account.id, []):
                unrealized_pnl = (pos.current_price - pos.entry_price) * pos.quantity
                if pos.side == "short":
                    unrealized_pnl = -unrealized_pnl
                total_pnl += unrealized_pnl

            # P0-2: 修复今日盈亏计算 - 从 Order 表汇总当日已成交订单的 pnl
            today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            today_orders = await self.order_repo.get_filled_orders_after(account.id, today_start)
            today_trade_count += len(today_orders)
            account_today_pnl = sum(
                (o.pnl for o in today_orders if o.pnl is not None), Decimal("0")
            )
            today_pnl += account_today_pnl

        # 计算收益率
        total_pnl_percent = (
            (total_pnl / initial_capital * 100) if initial_capital > 0 else Decimal("0")
        )
        today_pnl_percent = (
            (today_pnl / initial_capital * 100) if initial_capital > 0 else Decimal("0")
        )

        return {
            "totalAssets": float(total_asset + total_pnl),
            "totalPnl": float(total_pnl),
            "totalPnlPercent": float(total_pnl_percent),
            "availableBalance": float(available_balance),
            "frozenBalance": float(locked_balance),
            "todayPnl": float(today_pnl),
            "todayPnlPercent": float(today_pnl_percent),
            "todayTradeCount": today_trade_count,
            "updatedAt": datetime.now(UTC).isoformat() + "Z",
        }

    async def get_positions(
        self,
        user_id: int,
        exchange: str = "all",
        side: str = "all",
        account_id: int | None = None,
    ) -> list[dict]:
        """
        获取持仓列表

        Args:
            user_id: 用户ID
            exchange: 交易所筛选
            side: 方向筛选 (long/short/all)
            account_id: 指定账户筛选；None 表示全部

        Returns:
            list[dict]: 持仓列表（含 source 标签区分策略仓 / 外部仓）
        """
        accounts = await self.account_repo.get_active_by_user(user_id)
        if exchange != "all":
            accounts = [a for a in accounts if a.exchange == exchange]
        if account_id is not None:
            accounts = [a for a in accounts if a.id == account_id]

        account_ids = [a.id for a in accounts]
        all_positions = []
        if account_ids:
            pos_result = await self.session.execute(
                select(Position).where(
                    Position.account_id.in_(account_ids),
                    Position.status == "open",
                )
            )
            all_positions = list(pos_result.scalars().all())

        # 批量预取所有涉及的策略实例名称（避免 N+1）
        instance_ids = {p.strategy_instance_id for p in all_positions if p.strategy_instance_id}
        instance_names: dict[int, str] = {}
        if instance_ids:
            inst_result = await self.session.execute(
                select(StrategyInstance.id, StrategyInstance.name).where(
                    StrategyInstance.id.in_(instance_ids)
                )
            )
            instance_names = dict(inst_result.all())

        accounts_by_id = {a.id: a for a in accounts}

        positions_data = []
        for pos in all_positions:
            if side != "all" and pos.side != side:
                continue

            account = accounts_by_id.get(pos.account_id)
            if account is None:
                continue

            price_diff = pos.current_price - pos.entry_price
            if pos.side == "short":
                price_diff = -price_diff
            pnl = price_diff * pos.quantity
            pnl_percent = (
                (price_diff / pos.entry_price * 100) if pos.entry_price > 0 else Decimal("0")
            )

            positions_data.append(
                {
                    "id": f"pos_{pos.id}",
                    "positionId": pos.id,
                    "accountId": account.id,
                    "accountName": account.account_name or account.exchange,
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "quantity": float(pos.quantity),
                    "entryPrice": float(pos.entry_price),
                    "currentPrice": float(pos.current_price),
                    "unrealizedPnl": float(pnl),
                    "unrealizedPnlPercent": float(pnl_percent),
                    "leverage": pos.leverage,
                    "exchange": account.exchange,
                    "strategyInstanceId": pos.strategy_instance_id,
                    "strategyName": (
                        instance_names.get(pos.strategy_instance_id)
                        if pos.strategy_instance_id
                        else None
                    ),
                    "source": "strategy" if pos.strategy_instance_id else "external",
                    "updatedAt": (
                        pos.updated_at.isoformat() + "Z"
                        if pos.updated_at
                        else datetime.now(UTC).isoformat() + "Z"
                    ),
                }
            )

        return positions_data

    async def get_equity_curve(self, user_id: int, days: int = 30, exchange: str = "all") -> dict:
        """
        获取权益曲线数据

        优先用 daily_equity_snapshot 表里的真快照（SyncScheduler 每 5 分钟 upsert
        当天值）。snapshot 没数据的早期日子用反推 fallback：
            equity[day] = today_total_equity - sum(orders.pnl filled_at in (day, today])

        Args:
            user_id: 用户ID
            days: 查询天数
            exchange: 交易所筛选

        Returns:
            dict: 权益曲线及统计数据
        """
        from app.models.equity_snapshot import DailyEquitySnapshot

        accounts = await self.account_repo.get_active_by_user(user_id)
        if exchange != "all":
            accounts = [a for a in accounts if a.exchange == exchange]
        account_ids = [a.id for a in accounts]

        # 1. 收集所有 filled 订单（按日期 group 用于反推 + PerformanceCalculator）
        all_trades = []
        trades_by_date: dict = {}
        for account in accounts:
            orders = await self.order_repo.get_by_account(account.id, status="filled", limit=2000)
            for o in orders:
                if o.pnl is not None and o.filled_at:
                    rec = TradeRecord(
                        entry_price=o.price or Decimal("0"),
                        exit_price=o.avg_fill_price or Decimal("0"),
                        quantity=o.filled_quantity,
                        side=o.side,
                        entry_time=o.created_at,
                        exit_time=o.filled_at,
                        pnl=o.pnl,
                        commission=o.commission,
                    )
                    all_trades.append(rec)
                    trades_by_date.setdefault(o.filled_at.date(), []).append(rec)

        # 2. 拉账户当前合计权益（balance + frozen + 持仓估值）
        today = datetime.now(UTC).date()
        positions_value = Decimal("0")
        for account in accounts:
            for p in await self.position_repo.get_open_by_account(account.id):
                if p.current_price and p.quantity:
                    positions_value += p.current_price * p.quantity
        today_total_equity = (
            sum((a.balance or Decimal("0")) + (a.frozen_balance or Decimal("0")) for a in accounts)
            + positions_value
        )

        # 3. 拉 [today-days, today] 范围内的 snapshot，按 (account_id, date) 索引
        start_date = today - timedelta(days=days)
        snapshot_map: dict = {}  # date -> {account_id: total_equity}
        if account_ids:
            stmt = (
                select(DailyEquitySnapshot)
                .where(DailyEquitySnapshot.account_id.in_(account_ids))
                .where(DailyEquitySnapshot.snapshot_date >= start_date)
            )
            result = await self.session.execute(stmt)
            for snap in result.scalars():
                snapshot_map.setdefault(snap.snapshot_date, {})[snap.account_id] = snap.total_equity

        # 4. 生成每日点：snapshot 命中则用 sum；缺失则从 today_total_equity 反推
        # 反推公式：equity[d] = today_total_equity - sum(pnl filled_at in (d, today])
        points = []
        fallback_initial = today_total_equity
        for i in range(days, -1, -1):
            d = today - timedelta(days=i)
            daily_pnl = sum((t.pnl for t in trades_by_date.get(d, [])), Decimal("0"))

            if d in snapshot_map and len(snapshot_map[d]) == len(account_ids):
                equity_val = sum(snapshot_map[d].values(), Decimal("0"))
            else:
                # fallback：用今天总权益减去 d+1 到 today 的累计 PnL
                fwd_pnl = Decimal("0")
                for j in range(i):
                    fwd_d = today - timedelta(days=j)
                    fwd_pnl += sum((t.pnl for t in trades_by_date.get(fwd_d, [])), Decimal("0"))
                equity_val = today_total_equity - fwd_pnl
                if not fallback_initial or i == days:
                    fallback_initial = equity_val

            points.append(
                {
                    "date": d.strftime("%Y-%m-%d"),
                    "equity": float(equity_val),
                    "pnl": float(daily_pnl),
                }
            )

        # 5. 绩效指标用真实起点（曲线第一个点）算 PerformanceCalculator
        initial_capital = (
            Decimal(str(points[0]["equity"])) if points else self.DEFAULT_INITIAL_CAPITAL
        )
        if initial_capital <= 0:
            initial_capital = self.DEFAULT_INITIAL_CAPITAL
        report = PerformanceCalculator.calculate(trades=all_trades, initial_capital=initial_capital)

        return {
            "points": points,
            "totalReturn": float(report.total_return_pct),
            "maxDrawdown": float(-report.max_drawdown_pct),
            "sharpeRatio": float(report.sharpe_ratio),
            "winRate": float(report.win_rate),
            "totalTrades": report.total_trades,
            "profitFactor": float(report.profit_loss_ratio),
        }
