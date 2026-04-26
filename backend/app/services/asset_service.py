"""
资产服务 - 资产汇总、权益计算
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exchange import ExchangeAccount, Position
from app.models.order import Order
from app.models.strategy import StrategyInstance
from app.repositories.trading_repo import PositionRepository, OrderRepository, ExchangeAccountRepository
from app.repositories.strategy_repo import StrategyInstanceRepository
from app.core.performance import PerformanceCalculator, TradeRecord, EquityPoint


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

    async def get_asset_summary(
        self,
        user_id: int,
        exchange: str = "all"
    ) -> dict:
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
        total_pnl = Decimal("0")
        available_balance = Decimal("0")
        locked_balance = Decimal("0")
        today_pnl = Decimal("0")
        initial_capital = self.DEFAULT_INITIAL_CAPITAL

        # PRF-04: 批量加载所有持仓，避免 N+1 查询
        account_ids = [a.id for a in accounts]
        all_positions = []
        if account_ids:
            from sqlalchemy import select, or_
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
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            today_orders = await self.order_repo.get_filled_orders_after(account.id, today_start)
            account_today_pnl = sum((o.pnl for o in today_orders if o.pnl is not None), Decimal("0"))
            today_pnl += account_today_pnl

        # 计算收益率
        total_pnl_percent = (total_pnl / initial_capital * 100) if initial_capital > 0 else Decimal("0")
        today_pnl_percent = (today_pnl / initial_capital * 100) if initial_capital > 0 else Decimal("0")

        return {
            "totalAssets": float(total_asset + total_pnl),
            "totalPnl": float(total_pnl),
            "totalPnlPercent": float(total_pnl_percent),
            "availableBalance": float(available_balance),
            "frozenBalance": float(locked_balance),
            "todayPnl": float(today_pnl),
            "todayPnlPercent": float(today_pnl_percent),
            "updatedAt": datetime.now(timezone.utc).isoformat() + "Z",
        }

    async def get_positions(
        self,
        user_id: int,
        exchange: str = "all",
        side: str = "all"
    ) -> list[dict]:
        """
        获取持仓列表

        Args:
            user_id: 用户ID
            exchange: 交易所筛选
            side: 方向筛选 (long/short/all)

        Returns:
            list[dict]: 持仓列表
        """
        # 获取用户账户
        accounts = await self.account_repo.get_active_by_user(user_id)
        if exchange != "all":
            accounts = [a for a in accounts if a.exchange == exchange]

        # PRF-04: 批量加载持仓
        account_ids = [a.id for a in accounts]
        all_positions = []
        if account_ids:
            from sqlalchemy import select
            pos_result = await self.session.execute(
                select(Position).where(
                    Position.account_id.in_(account_ids),
                    Position.status == "open",
                )
            )
            all_positions = list(pos_result.scalars().all())

        positions_by_account: dict[int, list[Position]] = {}
        for pos in all_positions:
            positions_by_account.setdefault(pos.account_id, []).append(pos)

        positions_data = []
        for account in accounts:
            for pos in positions_by_account.get(account.id, []):
                # 方向筛选
                if side != "all" and pos.side != side:
                    continue

                # 计算盈亏
                price_diff = pos.current_price - pos.entry_price
                if pos.side == "short":
                    price_diff = -price_diff
                pnl = price_diff * pos.quantity
                pnl_percent = (price_diff / pos.entry_price * 100) if pos.entry_price > 0 else Decimal("0")

                positions_data.append({
                    "id": f"pos_{pos.id}",
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "quantity": float(pos.quantity),
                    "entryPrice": float(pos.entry_price),
                    "currentPrice": float(pos.current_price),
                    "unrealizedPnl": float(pnl),
                    "unrealizedPnlPercent": float(pnl_percent),
                    "leverage": pos.leverage,
                    "exchange": account.exchange,
                    "updatedAt": pos.updated_at.isoformat() + "Z" if pos.updated_at else datetime.now(timezone.utc).isoformat() + "Z",
                })

        return positions_data

    async def get_equity_curve(
        self,
        user_id: int,
        days: int = 30,
        exchange: str = "all"
    ) -> dict:
        """
        获取权益曲线数据

        Args:
            user_id: 用户ID
            days: 查询天数
            exchange: 交易所筛选

        Returns:
            dict: 权益曲线及统计数据
        """
        # 获取用户账户
        accounts = await self.account_repo.get_active_by_user(user_id)
        if exchange != "all":
            accounts = [a for a in accounts if a.exchange == exchange]

        # P0-1: 修复权益曲线 - 使用真实订单数据计算
        all_trades = []
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        for account in accounts:
            # 获取账户的所有历史成交订单
            orders = await self.order_repo.get_by_account(account.id, status="filled", limit=2000)
            for o in orders:
                if o.pnl is not None and o.filled_at:
                    # 简化：假设 entry_time 是 filled_at 之前的一个占位时间，如果模型中没有开仓时间的话
                    # 实际上 Order 模型应该记录 open_at 或类似的。这里我们主要关注 pnl 发生的时间
                    all_trades.append(TradeRecord(
                        entry_price=o.price or Decimal("0"),
                        exit_price=o.avg_fill_price or Decimal("0"),
                        quantity=o.filled_quantity,
                        side=o.side,
                        entry_time=o.created_at,
                        exit_time=o.filled_at,
                        pnl=o.pnl,
                        commission=o.commission
                    ))

        # 使用 PerformanceCalculator 计算绩效
        report = PerformanceCalculator.calculate(
            trades=all_trades,
            initial_capital=self.DEFAULT_INITIAL_CAPITAL
        )

        # 生成每日权益点
        points = []
        trades_by_date = {}
        for t in all_trades:
            d = t.exit_time.date()
            trades_by_date.setdefault(d, []).append(t)

        current_equity = self.DEFAULT_INITIAL_CAPITAL
        for i in range(days, -1, -1):
            date = (datetime.now(timezone.utc) - timedelta(days=i)).date()
            daily_pnl = sum((t.pnl for t in trades_by_date.get(date, [])), Decimal("0"))
            current_equity += daily_pnl
            points.append({
                "date": date.strftime("%Y-%m-%d"),
                "equity": float(current_equity),
                "pnl": float(daily_pnl),
            })

        return {
            "points": points,
            "totalReturn": float(report.total_return_pct),
            "maxDrawdown": float(-report.max_drawdown_pct),
            "sharpeRatio": float(report.sharpe_ratio),
            "winRate": float(report.win_rate),
            "totalTrades": report.total_trades,
            "profitFactor": float(report.profit_loss_ratio),
        }
