"""
资产服务 - 资产汇总、权益计算
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exchange import ExchangeAccount, Position
from app.models.order import Order
from app.models.strategy import StrategyInstance
from app.repositories.trading_repo import PositionRepository, OrderRepository, ExchangeAccountRepository
from app.repositories.strategy_repo import StrategyInstanceRepository


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

                # 今日盈亏（简化：使用当前价格与昨日收盘价对比）
                # 这里简化为总盈亏的1/30作为今日估算
                today_pnl += unrealized_pnl / 30

        # 计算收益率
        total_pnl_percent = (total_pnl / initial_capital * 100) if initial_capital > 0 else Decimal("0")
        today_pnl_percent = (today_pnl / initial_capital * 100) if initial_capital > 0 else Decimal("0")

        return {
            "totalAsset": float(total_asset + total_pnl),
            "totalPnL": float(total_pnl),
            "totalPnLPercent": float(total_pnl_percent),
            "availableBalance": float(available_balance),
            "lockedBalance": float(locked_balance),
            "todayPnL": float(today_pnl),
            "todayPnLPercent": float(today_pnl_percent),
            "updatedAt": datetime.utcnow().isoformat() + "Z",
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
                    "pnl": float(pnl),
                    "pnlPercent": float(pnl_percent),
                    "leverage": pos.leverage,
                    "exchange": account.exchange,
                    "updatedAt": pos.updated_at.isoformat() + "Z" if pos.updated_at else datetime.utcnow().isoformat() + "Z",
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

        # 生成权益曲线数据点
        points = []
        base_equity = self.DEFAULT_INITIAL_CAPITAL
        current_equity = base_equity

        for i in range(days, -1, -1):
            date = datetime.utcnow().date() - timedelta(days=i)
            # 模拟每日权益变化（实际应从数据库查询）
            daily_change = current_equity * Decimal("0.001") * (i % 10 - 5) / 10
            current_equity = current_equity + daily_change
            daily_pnl = daily_change

            points.append({
                "date": date.strftime("%Y-%m-%d"),
                "equity": float(current_equity),
                "dailyPnL": float(daily_pnl),
            })

        # 计算统计数据
        final_equity = current_equity
        total_return = ((final_equity - base_equity) / base_equity * 100) if base_equity > 0 else Decimal("0")

        # 计算最大回撤
        max_equity = base_equity
        max_drawdown = Decimal("0")
        for p in points:
            if p["equity"] > float(max_equity):
                max_equity = Decimal(str(p["equity"]))
            drawdown = ((max_equity - Decimal(str(p["equity"]))) / max_equity * 100)
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # 获取策略统计数据
        total_trades = 0
        win_trades = 0
        for account in accounts:
            # 获取账户的历史订单
            orders = await self.order_repo.get_by_account(account.id, limit=1000)
            closed_orders = [o for o in orders if o.status == "filled" and o.pnl is not None]
            total_trades += len(closed_orders)
            win_trades += len([o for o in closed_orders if o.pnl > 0])

        win_rate = (Decimal(str(win_trades)) / Decimal(str(total_trades)) * 100) if total_trades > 0 else Decimal("0")
        profit_factor = Decimal("2.1")  # 简化计算

        return {
            "points": points,
            "totalReturn": float(total_return),
            "maxDrawdown": float(-max_drawdown),
            "sharpeRatio": float(Decimal("2.35")),  # 简化
            "winRate": float(win_rate),
            "totalTrades": total_trades,
            "profitFactor": float(profit_factor),
        }
