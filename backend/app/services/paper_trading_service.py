"""
本地模拟盘（Paper Trading）服务

负责：
- 创建 / 重置本地模拟盘账户
- 维护本地资产余额
- 为手动交易页提供本地撮合所需的价格与资金更新
"""

import asyncio
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exchange import ExchangeAccount, Position

logger = logging.getLogger(__name__)


class PaperTradingService:
    """本地模拟盘服务"""

    DEFAULT_INITIAL_BALANCE = Decimal("100000")
    DEFAULT_COMMISSION_RATE = Decimal("0.001")
    DEFAULT_SLIPPAGE_PCT = Decimal("0.0005")

    _locks: dict[int, asyncio.Lock] = {}
    _locks_lock = asyncio.Lock()

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_lock(self, account_id: int) -> asyncio.Lock:
        async with self._locks_lock:
            if account_id not in self._locks:
                self._locks[account_id] = asyncio.Lock()
            return self._locks[account_id]

    @classmethod
    def default_balances(cls, initial_balance: Decimal | None = None) -> dict[str, str]:
        balance = initial_balance or cls.DEFAULT_INITIAL_BALANCE
        return {"USDT": format(balance, "f")}

    @staticmethod
    def is_paper_account(account: ExchangeAccount | None) -> bool:
        return bool(account and getattr(account, "is_paper", False))

    @staticmethod
    def normalize_symbol_key(symbol: str) -> str:
        return str(symbol or "").upper()

    @staticmethod
    def get_contract_settings(account: ExchangeAccount, symbol: str) -> dict[str, str | int]:
        settings = account.contract_settings or {}
        key = PaperTradingService.normalize_symbol_key(symbol)
        current = settings.get(key) or {}
        leverage = int(current.get("leverage") or 10)
        margin_mode = str(current.get("margin_mode") or "cross")
        return {
            "symbol": key,
            "leverage": leverage,
            "margin_mode": margin_mode,
        }

    async def create_paper_account(
        self,
        user_id: int,
        name: str = "本地模拟账户",
        initial_balance: Decimal = DEFAULT_INITIAL_BALANCE,
    ) -> ExchangeAccount:
        account = ExchangeAccount(
            user_id=user_id,
            account_name=name,
            exchange="binance",
            is_paper=True,
            is_demo=False,
            is_testnet=False,
            is_active=True,
            status="active",
            balance=initial_balance,
            frozen_balance=Decimal("0"),
            balances=self.default_balances(initial_balance),
            contract_settings={},
        )
        account.set_api_key(f"paper-key-{user_id}")
        account.set_secret_key(f"paper-secret-{user_id}")
        self.session.add(account)
        await self.session.flush()
        await self.session.refresh(account)
        logger.info("[PaperTrading] 创建本地模拟账户 #%d", account.id)
        return account

    async def get_paper_accounts(self, user_id: int) -> list[ExchangeAccount]:
        result = await self.session.execute(
            select(ExchangeAccount).where(
                ExchangeAccount.user_id == user_id,
                ExchangeAccount.is_paper,
            )
        )
        return list(result.scalars().all())

    async def reset_paper_account(
        self,
        account_id: int,
        new_balance: Decimal | None = None,
        *,
        user_id: int | None = None,
    ) -> ExchangeAccount:
        result = await self.session.execute(
            select(ExchangeAccount).where(
                ExchangeAccount.id == account_id,
                ExchangeAccount.is_paper,
            )
        )
        account = result.scalar_one_or_none()
        if not account:
            raise ValueError("模拟账户不存在")
        if user_id is not None and account.user_id != user_id:
            raise ValueError("无权重置此模拟账户")

        balance = new_balance or self.DEFAULT_INITIAL_BALANCE
        account.balance = balance
        account.frozen_balance = Decimal("0")
        account.balances = self.default_balances(balance)

        positions_result = await self.session.execute(
            select(Position).where(
                Position.account_id == account_id,
                Position.status == "open",
            )
        )
        for position in positions_result.scalars().all():
            position.status = "closed"

        await self.session.flush()
        logger.info("[PaperTrading] 重置本地模拟账户 #%d", account_id)
        return account

    async def get_execution_price(self, symbol: str, price: Decimal | None = None) -> Decimal:
        exec_price = price or await self._get_current_price(symbol)
        if exec_price is None:
            raise ValueError(f"无法获取 {symbol} 当前价格")
        return exec_price

    async def apply_spot_fill(
        self,
        account: ExchangeAccount,
        *,
        symbol: str,
        side: str,
        quantity: Decimal,
        exec_price: Decimal,
        commission: Decimal,
    ) -> None:
        base_asset, quote_asset = self._split_symbol(symbol)
        balances = dict(account.balances or self.default_balances(account.balance))
        quote_balance = Decimal(str(balances.get(quote_asset, "0")))
        base_balance = Decimal(str(balances.get(base_asset, "0")))
        order_value = exec_price * quantity

        if side == "buy":
            total_cost = order_value + commission
            if quote_balance < total_cost:
                raise ValueError(
                    f"模拟余额不足: 需要 {format(total_cost, 'f')} {quote_asset}，"
                    f" 当前只有 {format(quote_balance, 'f')} {quote_asset}"
                )
            quote_balance -= total_cost
            base_balance += quantity
        else:
            if base_balance < quantity:
                raise ValueError(
                    f"{base_asset} 余额不足: 需要 {format(quantity, 'f')}，"
                    f" 当前只有 {format(base_balance, 'f')}"
                )
            quote_balance += order_value - commission
            base_balance -= quantity

        balances[quote_asset] = format(quote_balance, "f")
        balances[base_asset] = format(base_balance, "f")
        account.balances = balances
        account.balance = quote_balance
        account.frozen_balance = Decimal("0")

    async def reserve_contract_margin(
        self,
        account: ExchangeAccount,
        *,
        symbol: str,
        quantity: Decimal,
        exec_price: Decimal,
        commission: Decimal = Decimal("0"),
    ) -> dict[str, Decimal | int | str]:
        settings = self.get_contract_settings(account, symbol)
        leverage = int(settings["leverage"])
        margin_mode = str(settings["margin_mode"])
        notional = exec_price * quantity
        required_margin = notional / Decimal(leverage)
        available = Decimal(str(account.balance or "0"))
        total_hold = required_margin + commission
        if available < total_hold:
            raise ValueError(
                f"保证金不足: 需要 {format(total_hold, 'f')} USDT，"
                f" 当前可用 {format(available, 'f')} USDT"
            )

        account.balance = available - total_hold
        account.frozen_balance = Decimal(str(account.frozen_balance or "0")) + required_margin
        balances = dict(account.balances or self.default_balances(available))
        balances["USDT"] = format(account.balance, "f")
        account.balances = balances
        return {
            "leverage": leverage,
            "margin_mode": margin_mode,
            "required_margin": required_margin,
            "notional": notional,
        }

    async def release_contract_margin(
        self,
        account: ExchangeAccount,
        *,
        position: Position,
        exit_price: Decimal,
        commission: Decimal,
    ) -> Decimal:
        leverage = max(int(getattr(position, "leverage", 1) or 1), 1)
        entry_notional = position.entry_price * position.quantity
        margin = entry_notional / Decimal(leverage)
        if position.side == "long":
            realized_pnl = (exit_price - position.entry_price) * position.quantity
        else:
            realized_pnl = (position.entry_price - exit_price) * position.quantity

        released = margin + realized_pnl - commission
        account.balance = Decimal(str(account.balance or "0")) + released
        frozen = Decimal(str(account.frozen_balance or "0")) - margin
        account.frozen_balance = frozen if frozen > 0 else Decimal("0")
        balances = dict(account.balances or self.default_balances(account.balance))
        balances["USDT"] = format(account.balance, "f")
        account.balances = balances
        return realized_pnl

    async def upsert_contract_settings(
        self,
        account: ExchangeAccount,
        *,
        symbol: str,
        leverage: int,
        margin_mode: str,
    ) -> dict[str, str | int]:
        settings = dict(account.contract_settings or {})
        key = self.normalize_symbol_key(symbol)
        settings[key] = {
            "leverage": int(leverage),
            "margin_mode": margin_mode,
        }
        account.contract_settings = settings
        await self.session.flush()
        return self.get_contract_settings(account, symbol)

    async def _get_current_price(self, symbol: str) -> Decimal | None:
        try:
            from app.services.market_service import MarketService

            market = MarketService()
            ticker = await market.get_ticker(symbol.replace(".P", ""))
            if ticker and ticker.get("last"):
                return Decimal(str(ticker["last"]))
        except Exception as exc:
            logger.debug("[PaperTrading] 获取行情失败: %s", exc)

        result = await self.session.execute(
            select(Position)
            .where(
                Position.symbol == symbol,
                Position.status == "open",
            )
            .order_by(Position.updated_at.desc())
            .limit(1)
        )
        position = result.scalar_one_or_none()
        if position and position.current_price:
            return position.current_price
        return None

    @staticmethod
    def _split_symbol(symbol: str) -> tuple[str, str]:
        raw = str(symbol or "").replace(".P", "").upper()
        for quote in ("USDT", "USDC", "BUSD", "BTC", "ETH"):
            if raw.endswith(quote):
                return raw[: -len(quote)], quote
        raise ValueError(f"不支持的交易对格式: {symbol}")
