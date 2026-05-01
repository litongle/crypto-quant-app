"""
模拟盘（Paper Trading）服务 - P2-9

不花真钱，用虚拟余额跑策略。支持：
- 创建模拟账户（带初始虚拟余额）
- 模拟下单（无API调用，直接更新本地状态）
- 模拟成交（自动 fill，模拟延迟和滑点）
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exchange import ExchangeAccount, Position

logger = logging.getLogger(__name__)


class PaperTradingService:
    """模拟盘服务"""

    # 默认模拟配置
    DEFAULT_INITIAL_BALANCE = Decimal("100000")
    DEFAULT_COMMISSION_RATE = Decimal("0.001")  # 0.1%
    DEFAULT_SLIPPAGE_PCT = Decimal("0.0005")    # 0.05% 滑点

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_paper_account(
        self, user_id: int, name: str = "模拟盘账户",
        initial_balance: Decimal = DEFAULT_INITIAL_BALANCE,
    ) -> ExchangeAccount:
        """创建模拟盘账户"""
        account = ExchangeAccount(
            user_id=user_id,
            account_name=name,
            exchange="paper",
            balances={"USDT": str(initial_balance)},
            is_demo=True,
            is_testnet=True,
            is_active=True,
            status="active",
        )
        self.session.add(account)
        await self.session.flush()
        await self.session.refresh(account)
        logger.info("[PaperTrading] 模拟账户创建: #%d, 初始余额 %s USDT", account.id, initial_balance)
        return account

    async def execute_paper_trade(
        self,
        account_id: int,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
        strategy_instance_id: int | None = None,
    ) -> dict[str, Any]:
        """执行模拟交易

        Args:
            account_id: 模拟账户ID
            symbol: 交易对
            side: buy/sell
            order_type: market/limit
            quantity: 数量
            price: 限价单价格（市价单不用传）
            strategy_instance_id: 关联策略实例

        Returns:
            订单信息
        """
        # 获取账户
        result = await self.session.execute(
            select(ExchangeAccount).where(
                ExchangeAccount.id == account_id,
                ExchangeAccount.is_demo == True,
            )
        )
        account = result.scalar_one_or_none()
        if not account:
            raise ValueError("模拟账户不存在或不是模拟账户")

        # 获取当前价格（模拟场景下使用本地持仓价格 or 从行情获取）
        exec_price = price or await self._get_current_price(symbol)
        if exec_price is None:
            raise ValueError(f"无法获取 {symbol} 当前价格")

        # 计算滑点
        slippage = exec_price * self.DEFAULT_SLIPPAGE_PCT
        if side == "buy":
            exec_price += slippage  # 买入时价格略高
        else:
            exec_price -= slippage  # 卖出时价格略低

        # 计算手续费
        commission = exec_price * quantity * self.DEFAULT_COMMISSION_RATE

        # 获取虚拟余额
        balances = account.balances or {"USDT": str(self.DEFAULT_INITIAL_BALANCE)}
        usdt_balance = Decimal(str(balances.get("USDT", "0")))

        # 检查余额
        order_value = exec_price * quantity
        total_cost = order_value + commission

        if side == "buy" and usdt_balance < total_cost:
            raise ValueError(f"模拟余额不足: 需要 {total_cost} USDT, 余额 {usdt_balance} USDT")

        # 更新余额
        if side == "buy":
            balances["USDT"] = str(usdt_balance - total_cost)
            # 更新持仓
            base_asset = symbol.replace("USDT", "")
            current_qty = Decimal(str(balances.get(base_asset, "0")))
            balances[base_asset] = str(current_qty + quantity)
        else:
            # 卖出检查
            base_asset = symbol.replace("USDT", "")
            current_qty = Decimal(str(balances.get(base_asset, "0")))
            if current_qty < quantity:
                raise ValueError(f"{base_asset} 余额不足: 需要 {quantity}, 余额 {current_qty}")
            sell_value = exec_price * quantity - commission
            balances["USDT"] = str(usdt_balance + sell_value)
            balances[base_asset] = str(current_qty - quantity)

        account.balances = balances

        # 创建订单记录
        order = {
            "account_id": account_id,
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": str(quantity),
            "price": str(exec_price),
            "avg_fill_price": str(exec_price),
            "filled_quantity": str(quantity),
            "commission": str(commission),
            "order_value": str(order_value),
            "status": "filled",
            "filled_at": datetime.now(timezone.utc).isoformat() + "Z",
            "strategy_instance_id": strategy_instance_id,
            "exec_price": float(exec_price),
            "slippage": float(slippage),
            "commission_paid": float(commission),
        }

        logger.info(
            "[PaperTrading] 模拟成交: %s %s %s @ %s, qty=%s, commission=%s",
            symbol, side, order_type, exec_price, quantity, commission,
        )
        return order

    async def _get_current_price(self, symbol: str) -> Decimal | None:
        """获取当前价格（从行情服务或现有持仓）"""
        try:
            from app.services.market_service import MarketService
            market = MarketService()
            ticker = await market.get_ticker(symbol)
            if ticker and ticker.get("last"):
                return Decimal(str(ticker["last"]))
        except Exception as exc:
            logger.debug("[PaperTrading] 获取行情失败: %s", exc)

        # 降级：从已有持仓获取
        result = await self.session.execute(
            select(Position).where(
                Position.symbol == symbol,
                Position.status == "open",
            ).order_by(Position.updated_at.desc()).limit(1)
        )
        pos = result.scalar_one_or_none()
        if pos and pos.current_price:
            return pos.current_price

        return None

    async def get_paper_accounts(self, user_id: int) -> list[ExchangeAccount]:
        """获取用户的所有模拟账户"""
        result = await self.session.execute(
            select(ExchangeAccount).where(
                ExchangeAccount.user_id == user_id,
                ExchangeAccount.is_demo == True,
            )
        )
        return list(result.scalars().all())

    async def reset_paper_account(self, account_id: int, new_balance: Decimal | None = None) -> None:
        """重置模拟账户余额"""
        result = await self.session.execute(
            select(ExchangeAccount).where(
                ExchangeAccount.id == account_id,
                ExchangeAccount.is_demo == True,
            )
        )
        account = result.scalar_one_or_none()
        if not account:
            raise ValueError("模拟账户不存在")

        balance = new_balance or self.DEFAULT_INITIAL_BALANCE
        account.balances = {"USDT": str(balance)}
        await self.session.flush()
        logger.info("[PaperTrading] 模拟账户 #%d 已重置, 余额 %s USDT", account_id, balance)
