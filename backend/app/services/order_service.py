"""
订单服务
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AppException,
    ExchangeAPIError,
    NetworkError,
    OrderRejectedError,
    RateLimitError,
)
from app.core.exchanges.base import OrderResult
from app.core.instrument_resolution import adapter_symbol_for_okx_order, resolve_execution_context
from app.core.trade_schemas import TradingSymbolRulesSchema
from app.models.exchange import ExchangeAccount, Position
from app.models.order import Order
from app.repositories.strategy_repo import StrategyInstanceRepository
from app.repositories.trading_repo import (
    ExchangeAccountRepository,
    OrderRepository,
    PositionRepository,
)
from app.services.paper_trading_service import PaperTradingService

if TYPE_CHECKING:
    from app.core.exchanges import OrderResult

logger = logging.getLogger(__name__)


class OrderService:
    """订单服务"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.account_repo = ExchangeAccountRepository(session)
        self.position_repo = PositionRepository(session)
        self.order_repo = OrderRepository(session)
        self.strategy_repo = StrategyInstanceRepository(session)

    async def get_user_accounts(
        self, user_id: int, *, include_paper: bool = False
    ) -> list[ExchangeAccount]:
        """获取用户的交易所账户"""
        accounts = await self.account_repo.get_active_by_user(user_id)
        if include_paper:
            return accounts
        return [account for account in accounts if not getattr(account, "is_paper", False)]

    @staticmethod
    def _is_paper_account(account: ExchangeAccount | None) -> bool:
        return PaperTradingService.is_paper_account(account)

    def _paper_service(self) -> PaperTradingService:
        return PaperTradingService(self.session)

    @staticmethod
    def _contract_symbol_key(symbol: str) -> str:
        return str(symbol or "").upper()

    def _get_saved_contract_settings(
        self, account: ExchangeAccount, symbol: str
    ) -> dict[str, str | int]:
        return self._paper_service().get_contract_settings(account, symbol)

    @staticmethod
    def _normalize_ui_symbol(symbol: str) -> tuple[str, str, bool]:
        base_symbol, is_perp = resolve_execution_context(symbol, None)
        normalized_base = base_symbol.upper()
        if not normalized_base.endswith(("USDT", "USDC", "BTC", "ETH")):
            normalized_base += "USDT"
        normalized_symbol = f"{normalized_base}.P" if is_perp else normalized_base
        return normalized_symbol, normalized_base, is_perp

    @staticmethod
    def _adapter_symbol_for_rules(exchange: str, base_symbol: str, is_perp: bool) -> str:
        exchange_lower = (exchange or "").lower()
        if is_perp and exchange_lower == "okx":
            return adapter_symbol_for_okx_order(base_symbol, True).upper()
        return base_symbol

    async def _get_adapter(self, account: ExchangeAccount, *, is_futures: bool = False):
        """获取交易所适配器助手 (P1-11: 统一解密逻辑)"""
        from app.core.exchange_adapter import get_exchange_adapter

        bin_fut = is_futures and account.exchange.lower() == "binance"
        adapter = get_exchange_adapter(
            exchange=account.exchange,
            api_key=account.get_api_key(),
            secret_key=account.get_secret_key(),
            passphrase=account.get_passphrase() if account.encrypted_passphrase else None,
            testnet=account.is_testnet,
            is_demo=account.is_demo,
            is_futures=bin_fut,
        )
        return adapter

    async def _adapter_exec_context_for_order(
        self, order: Order, account: ExchangeAccount
    ) -> tuple[str, bool]:
        """(交易所下单符号, Binance 是否走 U 本位合约 API)。"""
        strategy_params = None
        if order.strategy_instance_id:
            inst = await self.strategy_repo.get_by_id(order.strategy_instance_id)
            if inst:
                strategy_params = inst.params or {}
        sym_u, perp = resolve_execution_context(order.symbol, strategy_params)
        ex = (account.exchange or "").lower()
        bin_fut = perp and ex == "binance"
        sym_u = self._adapter_symbol_for_rules(ex, sym_u, perp)
        return sym_u, bin_fut

    async def _adapter_order_request_kwargs(
        self,
        *,
        order: Order,
        account: ExchangeAccount,
        closing_position: Position | None = None,
    ) -> dict[str, str]:
        strategy_params = None
        if order.strategy_instance_id:
            inst = await self.strategy_repo.get_by_id(order.strategy_instance_id)
            if inst:
                strategy_params = inst.params or {}
        _, is_perp = resolve_execution_context(order.symbol, strategy_params)
        exchange = (account.exchange or "").lower()
        kwargs: dict[str, str] = {}

        if exchange == "okx":
            if is_perp:
                if closing_position is not None:
                    kwargs["position_side"] = closing_position.side
                else:
                    kwargs["position_side"] = "long" if order.side == "buy" else "short"
            elif order.order_type == "market" and order.side == "buy":
                kwargs["target_currency"] = "base_ccy"

        return kwargs

    @staticmethod
    def _map_exchange_status(status_value: str | None) -> str:
        status_key = str(status_value or "").lower()
        status_map = {
            "canceled": "cancelled",
            "cancelled": "cancelled",
            "expired": "cancelled",
            "live": "submitted",
            "new": "submitted",
            "open": "submitted",
            "partially_filled": "partial",
            "partial-filled": "partial",
        }
        return status_map.get(status_key, status_key or "pending")

    def _apply_order_result(self, order: Order, result: OrderResult) -> str:
        if result.exchange_order_id:
            order.exchange_order_id = result.exchange_order_id

        mapped_status = self._map_exchange_status(result.status)
        order.status = mapped_status

        if result.filled_quantity > 0:
            order.filled_quantity = result.filled_quantity
        if result.avg_fill_price and result.avg_fill_price > 0:
            order.avg_fill_price = result.avg_fill_price
        if order.avg_fill_price and order.filled_quantity:
            order.order_value = order.avg_fill_price * order.filled_quantity

        if mapped_status == "filled" and not order.filled_at:
            order.filled_at = datetime.now(UTC)

        return mapped_status

    async def _refresh_recent_order_status(
        self,
        *,
        order: Order,
        account: ExchangeAccount,
        adapter,
        adapter_symbol: str,
        closing_position: Position | None = None,
    ) -> Order:
        if not order.exchange_order_id:
            return order

        pending_statuses = {"pending", "submitted", "partial"}
        if order.status not in pending_statuses:
            return order

        for delay in (0.0, 0.8, 1.6):
            if delay > 0:
                await asyncio.sleep(delay)

            try:
                refreshed = await adapter.get_order(order.exchange_order_id, adapter_symbol)
            except Exception as exc:
                logger.debug(
                    "[OrderService] 订单即时补查失败: order_id=%d, exchange_order_id=%s, error=%s",
                    order.id,
                    order.exchange_order_id,
                    exc,
                )
                continue

            previous_status = order.status
            mapped_status = self._apply_order_result(order, refreshed)
            should_sync_position = mapped_status == "filled" and previous_status != "filled"

            if should_sync_position:
                await self._sync_position_on_fill(order, account, refreshed)
                await self.session.refresh(order)
            else:
                await self.session.commit()
                await self.session.refresh(order)

            logger.info(
                "[OrderService] 订单即时补查: order_id=%d, status=%s",
                order.id,
                order.status,
            )

            if order.status not in pending_statuses:
                break

        return order

    async def _adapter_exec_context_for_position(
        self, position: Position, account: ExchangeAccount
    ) -> tuple[str, bool]:
        strategy_params = None
        if position.strategy_instance_id:
            inst = await self.strategy_repo.get_by_id(position.strategy_instance_id)
            if inst:
                strategy_params = inst.params or {}
        sym_u, perp = resolve_execution_context(position.symbol, strategy_params)
        ex = (account.exchange or "").lower()
        bin_fut = perp and ex == "binance"
        sym_u = self._adapter_symbol_for_rules(ex, sym_u, perp)
        return sym_u, bin_fut

    async def get_symbol_rules(
        self,
        *,
        user_id: int,
        account_id: int,
        symbol: str,
    ) -> TradingSymbolRulesSchema:
        """按账户 + 市场语义返回手动交易所需的精度/最小下单规则。"""
        account = await self.account_repo.get_by_id(account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="账户不存在",
            )
        if not account.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="账户已禁用",
            )

        normalized_symbol, normalized_base, is_perp = self._normalize_ui_symbol(symbol)
        exchange = (account.exchange or "").lower()
        adapter_symbol = self._adapter_symbol_for_rules(exchange, normalized_base, is_perp)
        adapter = await self._get_adapter(account, is_futures=is_perp and exchange == "binance")

        try:
            info = await adapter.get_exchange_info(adapter_symbol)
        except NotImplementedError as exc:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"{account.exchange} 暂不支持该市场的下单规则查询",
            ) from exc
        except ExchangeAPIError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"获取交易规则失败: {exc.message}",
            ) from exc
        except OrderRejectedError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"获取交易规则失败: {exc.message}",
            ) from exc

        return TradingSymbolRulesSchema.from_values(
            symbol=normalized_symbol,
            base_symbol=normalized_base,
            exchange_symbol=adapter_symbol,
            exchange=exchange,
            market_type="perp" if is_perp else "spot",
            min_qty=info.min_qty,
            step_size=info.step_size,
            min_notional=info.min_notional,
            tick_size=info.tick_size,
        )

    async def get_contract_settings(
        self,
        *,
        user_id: int,
        account_id: int,
        symbol: str,
    ) -> dict[str, str | int | bool]:
        account = await self.account_repo.get_by_id(account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账户不存在")

        normalized_symbol, _, is_perp = self._normalize_ui_symbol(symbol)
        if not is_perp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只有合约交易对支持杠杆与保证金模式设置",
            )

        settings = self._get_saved_contract_settings(account, normalized_symbol)
        return {
            **settings,
            "account_id": account_id,
            "is_paper": self._is_paper_account(account),
        }

    async def update_contract_settings(
        self,
        *,
        user_id: int,
        account_id: int,
        symbol: str,
        leverage: int,
        margin_mode: str,
    ) -> dict[str, str | int | bool]:
        account = await self.account_repo.get_by_id(account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账户不存在")
        if not account.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账户已禁用")
        if leverage < 1 or leverage > 125:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="杠杆范围应为 1-125"
            )
        if margin_mode not in {"cross", "isolated"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="保证金模式仅支持 cross 或 isolated",
            )

        normalized_symbol, normalized_base, is_perp = self._normalize_ui_symbol(symbol)
        if not is_perp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只有合约交易对支持杠杆与保证金模式设置",
            )

        if self._is_paper_account(account):
            settings = await self._paper_service().upsert_contract_settings(
                account,
                symbol=normalized_symbol,
                leverage=leverage,
                margin_mode=margin_mode,
            )
            return {
                **settings,
                "account_id": account_id,
                "is_paper": True,
            }

        exchange = (account.exchange or "").lower()
        adapter_symbol = self._adapter_symbol_for_rules(exchange, normalized_base, True)
        adapter = await self._get_adapter(account, is_futures=exchange == "binance")
        try:
            await adapter.configure_contract(
                adapter_symbol,
                leverage=leverage,
                margin_mode=margin_mode,
            )
        except NotImplementedError as exc:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"{account.exchange} 暂不支持通过控制台设置合约参数",
            ) from exc
        except ExchangeAPIError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"合约参数设置失败: {exc.message}",
            ) from exc
        except OrderRejectedError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"合约参数设置被拒绝: {exc.message}",
            ) from exc

        settings = await self._paper_service().upsert_contract_settings(
            account,
            symbol=normalized_symbol,
            leverage=leverage,
            margin_mode=margin_mode,
        )
        return {
            **settings,
            "account_id": account_id,
            "is_paper": False,
        }

    async def sync_account_balance(
        self, account_id: int, user_id: int | None = None, *, is_futures: bool = False
    ) -> ExchangeAccount:
        """从交易所同步账户真实余额

        调用交易所 get_balance() API，将 USDT 余额写回 ExchangeAccount。
        IDOR 修复：如果传入 user_id，验证账户所有权。
        """
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="账户不存在",
            )
        # IDOR 修复：验证账户所有权
        if user_id is not None and account.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作此账户",
            )

        if self._is_paper_account(account):
            balances = account.balances or PaperTradingService.default_balances(account.balance)
            account.balance = Decimal(str(balances.get("USDT", account.balance or "0")))
            account.frozen_balance = Decimal(str(account.frozen_balance or "0"))
            account.last_sync_at = datetime.now(UTC)
            account.status = "active"
            account.error_message = None
            await self.session.commit()
            await self.session.refresh(account)
            return account

        try:
            bin_fut = is_futures and account.exchange.lower() == "binance"
            adapter = await self._get_adapter(account, is_futures=bin_fut)
            balances = await adapter.get_balance()

            # 提取 USDT 余额
            for b in balances:
                if b.asset.upper() == "USDT":
                    account.balance = b.free
                    account.frozen_balance = b.locked
                    break
            else:
                # 没有 USDT 余额，尝试取第一个非零资产折算
                if balances:
                    account.balance = balances[0].free
                    account.frozen_balance = balances[0].locked

            account.last_sync_at = datetime.now(UTC)
            account.status = "active"
            account.error_message = None

            await self.session.commit()
            await self.session.refresh(account)

            logger.info(
                "[OrderService] 余额同步成功: account_id=%d, exchange=%s, "
                "balance=%.4f USDT, frozen=%.4f",
                account_id,
                account.exchange,
                float(account.balance),
                float(account.frozen_balance),
            )
            return account

        except Exception as exc:
            account.status = "error"
            account.error_message = f"余额同步失败: {str(exc)[:200]}"
            await self.session.commit()
            await self.session.refresh(account)

            logger.error(
                "[OrderService] 余额同步失败: account_id=%d, exchange=%s, error=%s",
                account_id,
                account.exchange,
                str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"余额同步失败: {str(exc)}",
            ) from exc

    async def create_order(
        self,
        user_id: int,
        account_id: int,
        symbol: str,
        side: Literal["buy", "sell"],
        order_type: Literal["market", "limit"],
        quantity: Decimal,
        price: Decimal | None = None,
        strategy_instance_id: int | None = None,
    ) -> Order:
        """
        创建订单
        """
        # 验证账户
        account = await self.account_repo.get_by_id(account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="账户不存在",
            )
        if not account.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="账户已禁用",
            )

        # 验证策略（如果指定）
        if strategy_instance_id:
            strategy = await self.strategy_repo.get_by_id(strategy_instance_id)
            if not strategy or strategy.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="策略不存在",
                )

        # 计算订单价值
        if order_type == "market":
            # 市价单：标记为待计算，提交到交易所后根据成交价更新
            order_value = Decimal("0")  # 提交后由交易所返回的实际成交价计算
        elif price and price > 0:
            order_value = quantity * price
        else:
            order_value = Decimal("0")

        # 生成幂等性客户端订单ID（P0-2: 超时重试时复用同一 ID）
        client_order_id = f"cq-{user_id}-{account_id}-{uuid.uuid4().hex[:12]}"

        # 创建订单
        order = Order(
            account_id=account_id,
            symbol=symbol.upper(),
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            order_value=order_value,
            status="pending",
            strategy_instance_id=strategy_instance_id,
            client_order_id=client_order_id,
        )
        return await self.order_repo.create(order)

    async def submit_order(
        self,
        order_id: int,
        user_id: int,
        *,
        closing_position: Position | None = None,
    ) -> Order:
        """提交订单到交易所（真实下单，带幂等性保护）"""
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="订单不存在",
            )

        account = await self.account_repo.get_by_id(order.account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作此订单",
            )

        # P0-2: 幂等性保护 — 已非 pending 的订单直接返回
        if order.status != "pending":
            logger.info(
                "[OrderService] 订单已提交过，幂等返回: order_id=%d, status=%s",
                order_id,
                order.status,
            )
            return order

        if self._is_paper_account(account):
            return await self._submit_paper_order(order, account, closing_position=closing_position)

        # 调用真实交易所 API
        try:
            adapter_sym, bin_fut = await self._adapter_exec_context_for_order(order, account)
            adapter = await self._get_adapter(account, is_futures=bin_fut)
            order_kwargs = await self._adapter_order_request_kwargs(
                order=order,
                account=account,
                closing_position=closing_position,
            )

            logger.info(
                "[OrderService] 提交订单: order_id=%d, symbol=%s, side=%s, "
                "exchange=%s, demo=%s, testnet=%s, client_order_id=%s",
                order_id,
                adapter_sym,
                order.side,
                account.exchange,
                account.is_demo,
                account.is_testnet,
                order.client_order_id,
            )

            result = await adapter.create_order(
                symbol=adapter_sym,
                side=order.side,
                order_type=order.order_type,
                quantity=order.quantity,
                price=order.price,
                **order_kwargs,
            )

            # 更新订单状态
            self._apply_order_result(order, result)
            order.submitted_at = datetime.now(UTC)

            logger.info(
                "[OrderService] 订单提交成功: order_id=%d, exchange_order_id=%s, status=%s",
                order_id,
                result.exchange_order_id,
                result.status,
            )

            await self.session.commit()
            await self.session.refresh(order)

            # 评审问题4: 订单成交后自动创建/更新 Position 记录
            if order.status == "filled":
                await self._sync_position_on_fill(order, account, result)
            elif order.status in {"pending", "submitted", "partial"}:
                await self._refresh_recent_order_status(
                    order=order,
                    account=account,
                    adapter=adapter,
                    adapter_symbol=adapter_sym,
                    closing_position=closing_position,
                )

            # P0-1: 大额成交通知（订单价值 > 1000 USDT）
            if order.order_value and order.order_value >= Decimal("1000"):
                try:
                    from app.services.notification_service import notify_large_trade

                    await notify_large_trade(
                        symbol=order.symbol,
                        side=order.side,
                        order_type=order.order_type,
                        quantity=order.quantity,
                        price=order.avg_fill_price or order.price or Decimal("0"),
                        order_value=order.order_value,
                        order_id=order.id,
                    )
                except Exception as exc:
                    logger.warning("[OrderService] 大额成交通知失败: %s", exc)

            return order

        except OrderRejectedError as exc:
            # 交易所明确拒绝（余额不足/风控/参数错误）→ 标记 rejected
            order.status = "rejected"
            order.error_message = f"订单被拒: {exc.message}"
            await self.session.commit()
            await self.session.refresh(order)
            logger.warning(
                "[OrderService] 订单被拒: order_id=%d, exchange=%s, code=%s, msg=%s",
                order_id,
                exc.exchange,
                exc.detail_code,
                exc.message,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"订单被交易所拒绝: {exc.message}",
            ) from exc

        except RateLimitError as exc:
            # 限流 → 不改状态，让前端可重试
            logger.warning(
                "[OrderService] 交易所限流: order_id=%d, exchange=%s",
                order_id,
                exc.exchange,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="交易所请求频率超限，请稍后重试",
            ) from exc

        except NetworkError as exc:
            # 网络异常 → 标记 pending（可能已提交但未确认）
            order.error_message = f"网络异常: {exc.message}"
            await self.session.commit()
            await self.session.refresh(order)
            logger.error(
                "[OrderService] 网络异常: order_id=%d, exchange=%s, msg=%s",
                order_id,
                exc.exchange,
                exc.message,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"交易所网络异常，请检查订单状态: {exc.message}",
            ) from exc

        except ExchangeAPIError as exc:
            # 其他交易所错误 → 标记 rejected
            order.status = "rejected"
            order.error_message = f"交易所错误: {exc.message}"
            await self.session.commit()
            await self.session.refresh(order)
            logger.error(
                "[OrderService] 交易所API错误: order_id=%d, exchange=%s, code=%s, retryable=%s",
                order_id,
                exc.exchange,
                exc.detail_code,
                exc.retryable,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"交易所下单失败: {exc.message}",
            ) from exc

        except AppException:
            raise
        except Exception as e:
            order.status = "rejected"
            order.error_message = f"下单失败: {str(e)}"
            await self.session.commit()
            await self.session.refresh(order)
            logger.exception(
                "[OrderService] 下单未知异常: order_id=%d",
                order_id,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"交易所下单失败: {str(e)}",
            ) from e

    async def _submit_paper_order(
        self,
        order: Order,
        account: ExchangeAccount,
        *,
        closing_position: Position | None = None,
    ) -> Order:
        paper = self._paper_service()

        try:
            exec_price = await paper.get_execution_price(order.symbol, order.price)
            slippage = exec_price * paper.DEFAULT_SLIPPAGE_PCT
            adjusted_price = exec_price + slippage if order.side == "buy" else exec_price - slippage
            commission = adjusted_price * order.quantity * paper.DEFAULT_COMMISSION_RATE

            async with await paper._get_lock(account.id):
                if order.symbol.endswith(".P"):
                    if closing_position is not None:
                        realized_pnl = await paper.release_contract_margin(
                            account,
                            position=closing_position,
                            exit_price=adjusted_price,
                            commission=commission,
                        )
                        order.pnl = realized_pnl
                    else:
                        await paper.reserve_contract_margin(
                            account,
                            symbol=order.symbol,
                            quantity=order.quantity,
                            exec_price=adjusted_price,
                            commission=commission,
                        )
                else:
                    await paper.apply_spot_fill(
                        account,
                        symbol=order.symbol,
                        side=order.side,
                        quantity=order.quantity,
                        exec_price=adjusted_price,
                        commission=commission,
                    )

                order.exchange_order_id = f"PAPER-{order.id}"
                order.status = "filled"
                order.submitted_at = datetime.now(UTC)
                order.filled_at = datetime.now(UTC)
                order.filled_quantity = order.quantity
                order.avg_fill_price = adjusted_price
                order.order_value = adjusted_price * order.quantity
                order.commission = commission

            await self.session.commit()
            await self.session.refresh(order)

            if closing_position is None:
                synthetic = OrderResult(
                    exchange_order_id=order.exchange_order_id or f"PAPER-{order.id}",
                    symbol=order.symbol,
                    side=order.side,
                    order_type=order.order_type,
                    quantity=order.quantity,
                    price=order.price,
                    status="filled",
                    filled_quantity=order.quantity,
                    avg_fill_price=adjusted_price,
                )
                await self._sync_position_on_fill(order, account, synthetic)

            return order
        except ValueError as exc:
            order.status = "rejected"
            order.error_message = str(exc)
            await self.session.commit()
            await self.session.refresh(order)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    async def cancel_order(self, order_id: int, user_id: int) -> Order:
        """取消订单（真实撤单）"""
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="订单不存在",
            )

        account = await self.account_repo.get_by_id(order.account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作此订单",
            )

        if order.status not in ["pending", "submitted", "partial"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"订单状态{order.status}无法取消",
            )

        # 调用交易所撤单
        if order.exchange_order_id:
            try:
                adapter_sym, bin_fut = await self._adapter_exec_context_for_order(order, account)
                adapter = await self._get_adapter(account, is_futures=bin_fut)

                logger.info(
                    "[OrderService] 撤单: order_id=%d, exchange_order_id=%s, symbol=%s",
                    order_id,
                    order.exchange_order_id,
                    adapter_sym,
                )

                success = await adapter.cancel_order(order.exchange_order_id, adapter_sym)
                if not success:
                    logger.warning(
                        "[OrderService] 撤单未成功: order_id=%d, exchange_order_id=%s",
                        order_id,
                        order.exchange_order_id,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="交易所撤单失败",
                    )
            except OrderRejectedError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"撤单被拒: {exc.message}",
                ) from exc
            except RateLimitError as exc:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="交易所请求频率超限，请稍后重试",
                ) from exc
            except NetworkError as exc:
                logger.error(
                    "[OrderService] 撤单网络异常: order_id=%d, msg=%s",
                    order_id,
                    exc.message,
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"交易所网络异常: {exc.message}",
                ) from exc
            except ExchangeAPIError as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"交易所撤单失败: {exc.message}",
                ) from exc
            except AppException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"交易所撤单失败: {str(e)}",
                ) from e

        order.status = "cancelled"
        order.cancelled_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def get_order_history(
        self,
        user_id: int,
        account_id: int | None = None,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[Order]:
        """获取订单历史"""
        accounts = await self.account_repo.get_active_by_user(user_id)
        if not accounts:
            return []

        all_orders = []
        for account in accounts:
            if account_id and account.id != account_id:
                continue
            orders = await self.order_repo.get_by_account(account.id, limit=limit)
            all_orders.extend(orders)

        if symbol:
            all_orders = [o for o in all_orders if o.symbol == symbol.upper()]

        all_orders.sort(key=lambda x: x.created_at, reverse=True)
        return all_orders[:limit]

    async def get_open_positions(
        self, user_id: int, account_id: int | None = None
    ) -> list[Position]:
        """获取持仓"""
        accounts = await self.account_repo.get_active_by_user(user_id)
        if not accounts:
            return []

        all_positions = []
        for account in accounts:
            if account_id and account.id != account_id:
                continue
            positions = await self.position_repo.get_open_by_account(account.id)
            all_positions.extend(positions)

        return all_positions

    async def close_position(
        self,
        position_id: int,
        user_id: int,
        *,
        pause_running_strategy: bool = False,
        pause_reason: str = "manual_close",
    ) -> Position:
        """平仓 — P1-1: 交易所成功后再标记 closed，使用事务安全顺序

        当 ``pause_running_strategy=True`` 且本仓位由策略开出时，会在标记 closed
        的同一事务里把仍在 running 的策略实例切到 paused —— 单次 commit 保证
        "仓位已平 / 策略仍在跑"这种不一致状态不会落库。

        默认 ``False`` 是为了不影响 strategy_runner 自我平仓（take-profit 等）的
        正常流程：策略主动平自己的仓位不应该让策略自己暂停。

        返回值约定：
            返回的 Position 对象额外挂载一个 ``strategy_paused: bool`` transient
            属性（非持久化字段），表示本次调用是否真的把策略切到 paused。
            调用方应使用 ``getattr(position, "strategy_paused", False)`` 读取，
            以容忍未来移除此契约的可能。
        """
        position = await self.position_repo.get_by_id(position_id)
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="持仓不存在",
            )

        account = await self.account_repo.get_by_id(position.account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作",
            )

        if position.status != "open":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="持仓已平仓",
            )

        side = "sell" if position.side == "long" else "buy"
        order = await self.create_order(
            user_id=user_id,
            account_id=position.account_id,
            symbol=position.symbol,
            side=side,
            order_type="market",
            quantity=position.quantity,
            strategy_instance_id=position.strategy_instance_id,
        )

        # P1-1: 先提交到交易所，成功后再更新 position 状态
        # submit_order 内部已有异常处理，失败会抛出 HTTPException
        await self.submit_order(
            order.id,
            user_id,
            closing_position=position,
        )

        # 计算盈亏并回写到平仓订单（让绩效报告能基于 orders.pnl 统计）
        realized_pnl = Decimal("0")
        if order.avg_fill_price and position.entry_price:
            if position.side == "long":
                realized_pnl = (order.avg_fill_price - position.entry_price) * position.quantity
            else:
                realized_pnl = (position.entry_price - order.avg_fill_price) * position.quantity
        order.pnl = realized_pnl

        # 在同一事务里更新策略实例：统计回写（total_trades / total_pnl / win_rate）
        # + 按需暂停。一次 commit 保证"仓位 closed / 统计 / 暂停状态"一致。
        strategy_paused = False
        instance = None
        if position.strategy_instance_id:
            instance = await self.strategy_repo.get_by_id(position.strategy_instance_id)

        if instance is not None:
            # 统计回写：close_position 即"一笔完整交易终结"
            prev_trades = instance.total_trades or 0
            prev_wins = int(round(float(instance.win_rate or 0) * prev_trades / 100))
            new_trades = prev_trades + 1
            new_wins = prev_wins + (1 if realized_pnl > 0 else 0)
            instance.total_trades = new_trades
            instance.total_pnl = (instance.total_pnl or Decimal("0")) + realized_pnl
            instance.win_rate = Decimal(str(round(new_wins / new_trades * 100, 2)))
            try:
                initial_capital = Decimal(str(instance.params.get("initial_capital", 100000)))
                if initial_capital > 0:
                    instance.total_pnl_percent = instance.total_pnl / initial_capital * 100
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                logger.debug("[OrderService] 计算 total_pnl_percent 跳过: %s", exc)

            if pause_running_strategy and instance.status == "running":
                instance.status = "paused"
                instance.last_pause_reason = pause_reason
                strategy_paused = True
                logger.info(
                    "[OrderService] 手动平策略 #%d 的仓位 #%d → 已同事务暂停该策略 (reason=%s)",
                    instance.id,
                    position.id,
                    pause_reason,
                )

        # 只有交易所确认成功后才标记平仓
        position.status = "closed"
        position.closed_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(position)

        if instance is not None:
            logger.info(
                "[OrderService] 策略 #%d 平仓 #%d 盈亏=%s, 累计交易=%d, 累计盈亏=%s",
                instance.id,
                position.id,
                realized_pnl,
                instance.total_trades,
                instance.total_pnl,
            )

        # 把暂停结果作为 transient 属性挂到 position 上供调用方读取（非持久化字段）
        position.strategy_paused = strategy_paused  # type: ignore[attr-defined]

        # P0-1: 止损/止盈触发通知
        try:
            if position.stop_loss_price and order.avg_fill_price:
                # 判断是否触发止损
                sl_triggered = False
                if (
                    position.side == "long"
                    and order.avg_fill_price <= position.stop_loss_price
                    or position.side == "short"
                    and order.avg_fill_price >= position.stop_loss_price
                ):
                    sl_triggered = True

                if sl_triggered:
                    from app.services.notification_service import notify_stop_loss

                    await notify_stop_loss(
                        symbol=position.symbol,
                        side=position.side,
                        entry_price=position.entry_price,
                        stop_price=position.stop_loss_price,
                        exit_price=order.avg_fill_price,
                        pnl=realized_pnl,
                        quantity=position.quantity,
                        position_id=position.id,
                    )

            if position.take_profit_price and order.avg_fill_price:
                # 判断是否触发止盈
                tp_triggered = False
                if (
                    position.side == "long"
                    and order.avg_fill_price >= position.take_profit_price
                    or position.side == "short"
                    and order.avg_fill_price <= position.take_profit_price
                ):
                    tp_triggered = True

                if tp_triggered:
                    from app.services.notification_service import notify_take_profit

                    await notify_take_profit(
                        symbol=position.symbol,
                        side=position.side,
                        entry_price=position.entry_price,
                        tp_price=position.take_profit_price,
                        exit_price=order.avg_fill_price,
                        pnl=realized_pnl,
                        quantity=position.quantity,
                        position_id=position.id,
                    )
        except Exception as exc:
            logger.warning("[OrderService] 止损/止盈通知失败: %s", exc)

        return position

    async def emergency_close_all(self, user_id: int, account_id: int | None = None):
        """紧急一键平仓（风控核心功能）"""
        accounts = await self.account_repo.get_active_by_user(user_id)
        closed_positions = []

        for account in accounts:
            if account_id and account.id != account_id:
                continue
            positions = await self.position_repo.get_open_by_account(account.id)
            for position in positions:
                await self.close_position(position.id, user_id)
                closed_positions.append(position)

        return closed_positions

    async def set_stop_loss(self, position_id: int, user_id: int, stop_price: Decimal) -> Position:
        """设置止损价格 — P0-3: 同时提交交易所条件单"""
        position = await self.position_repo.get_by_id(position_id)
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="持仓不存在",
            )

        account = await self.account_repo.get_by_id(position.account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作",
            )

        if position.status != "open":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="持仓已平仓",
            )

        # 验证止损价格合理性
        if position.side == "long" and stop_price >= position.entry_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="多头止损价必须低于开仓价",
            )
        if position.side == "short" and stop_price <= position.entry_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="空头止损价必须高于开仓价",
            )

        # P0-3: 实际向交易所提交止损条件单
        # 止损方向与持仓方向相反：多头持仓 → 卖出止损，空头持仓 → 买入止损
        sl_side = "sell" if position.side == "long" else "buy"
        try:
            adapter_sym, bin_fut = await self._adapter_exec_context_for_position(position, account)
            adapter = await self._get_adapter(account, is_futures=bin_fut)

            result = await adapter.create_stop_order(
                symbol=adapter_sym,
                side=sl_side,
                quantity=position.quantity,
                stop_price=stop_price,
                order_type="stop_loss",
            )

            # 保存交易所条件单ID
            if result.exchange_order_id:
                position.stop_loss_order_id = result.exchange_order_id

            logger.info(
                "[OrderService] 止损条件单已提交: position_id=%d, symbol=%s, "
                "stop_price=%s, exchange_order_id=%s",
                position_id,
                position.symbol,
                stop_price,
                result.exchange_order_id,
            )

        except Exception as exc:
            # 条件单提交失败时仍保存本地止损价（降级模式）
            logger.warning(
                "[OrderService] 止损条件单提交失败，降级为本地止损: position_id=%d, error=%s",
                position_id,
                str(exc),
            )

        position.stop_loss_price = stop_price
        await self.session.commit()
        await self.session.refresh(position)
        return position

    async def set_take_profit(self, position_id: int, user_id: int, tp_price: Decimal) -> Position:
        """设置止盈价格 — P0-3: 同时提交交易所条件单"""
        position = await self.position_repo.get_by_id(position_id)
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="持仓不存在",
            )

        account = await self.account_repo.get_by_id(position.account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作",
            )

        if position.status != "open":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="持仓已平仓",
            )

        # 验证止盈价格合理性
        if position.side == "long" and tp_price <= position.entry_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="多头止盈价必须高于开仓价",
            )
        if position.side == "short" and tp_price >= position.entry_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="空头止盈价必须低于开仓价",
            )

        # P0-3: 实际向交易所提交止盈条件单
        # 止盈方向与持仓方向相反：多头持仓 → 卖出止盈，空头持仓 → 买入止盈
        tp_side = "sell" if position.side == "long" else "buy"
        try:
            adapter_sym, bin_fut = await self._adapter_exec_context_for_position(position, account)
            adapter = await self._get_adapter(account, is_futures=bin_fut)

            result = await adapter.create_stop_order(
                symbol=adapter_sym,
                side=tp_side,
                quantity=position.quantity,
                stop_price=tp_price,
                order_type="take_profit",
            )

            # 保存交易所条件单ID
            if result.exchange_order_id:
                position.take_profit_order_id = result.exchange_order_id

            logger.info(
                "[OrderService] 止盈条件单已提交: position_id=%d, symbol=%s, "
                "tp_price=%s, exchange_order_id=%s",
                position_id,
                position.symbol,
                tp_price,
                result.exchange_order_id,
            )

        except Exception as exc:
            # 条件单提交失败时仍保存本地止盈价（降级模式）
            logger.warning(
                "[OrderService] 止盈条件单提交失败，降级为本地止盈: position_id=%d, error=%s",
                position_id,
                str(exc),
            )

        position.take_profit_price = tp_price
        await self.session.commit()
        await self.session.refresh(position)
        return position

    async def _sync_position_on_fill(
        self,
        order: Order,
        account,
        result: OrderResult,
    ) -> None:
        """订单成交后同步 DB Position 记录。

        按 "订单目标方向 vs 现有持仓方向" 分派 — 不能只看 order.side：
          buy  对应 target=long （想要的最终持仓方向）
          sell 对应 target=short

        在同 instance + 同 symbol 范围内查 open 持仓：
          - 有 target 方向持仓     → 加仓（加权平均开仓价）
          - 有反向持仓             → 平仓（status=closed）
          - 无持仓                 → 新建 target 方向持仓
        """
        try:
            leverage = 1
            if order.symbol.endswith(".P"):
                leverage = int(self._get_saved_contract_settings(account, order.symbol)["leverage"])

            target_side = "long" if order.side == "buy" else "short"
            opposite_side = "short" if target_side == "long" else "long"

            existing = await self.position_repo.get_by_account_and_symbol(
                order.account_id,
                order.symbol,
            )
            same_dir = next(
                (
                    p
                    for p in existing
                    if p.status == "open"
                    and p.strategy_instance_id == order.strategy_instance_id
                    and p.side == target_side
                ),
                None,
            )
            opp_dir = next(
                (
                    p
                    for p in existing
                    if p.status == "open"
                    and p.strategy_instance_id == order.strategy_instance_id
                    and p.side == opposite_side
                ),
                None,
            )

            if same_dir:
                # 加仓：加权平均开仓价
                total_qty = same_dir.quantity + order.filled_quantity
                if order.avg_fill_price:
                    weighted_price = (
                        same_dir.entry_price * same_dir.quantity
                        + order.avg_fill_price * order.filled_quantity
                    ) / total_qty
                    same_dir.entry_price = weighted_price
                same_dir.quantity = total_qty
                same_dir.current_price = order.avg_fill_price or same_dir.current_price
                same_dir.leverage = leverage
                same_dir.updated_at = datetime.now(UTC)
                logger.info(
                    "[OrderService] 加仓 Position #%d (side=%s): qty=%s, avg_price=%s",
                    same_dir.id,
                    same_dir.side,
                    same_dir.quantity,
                    same_dir.entry_price,
                )
            elif opp_dir:
                # 平反向仓
                opp_dir.status = "closed"
                opp_dir.closed_at = datetime.now(UTC)
                logger.info(
                    "[OrderService] 平仓 Position #%d (side=%s)",
                    opp_dir.id,
                    opp_dir.side,
                )
            else:
                # 新建 target_side 持仓
                new_pos = Position(
                    account_id=order.account_id,
                    symbol=order.symbol,
                    side=target_side,
                    quantity=order.filled_quantity,
                    entry_price=order.avg_fill_price or Decimal("0"),
                    current_price=order.avg_fill_price or Decimal("0"),
                    leverage=leverage,
                    status="open",
                    strategy_instance_id=order.strategy_instance_id,
                    opened_at=datetime.now(UTC),
                )
                self.session.add(new_pos)
                await self.session.flush()
                logger.info(
                    "[OrderService] 新建 %s Position #%d: symbol=%s, qty=%s",
                    target_side,
                    new_pos.id,
                    order.symbol,
                    order.filled_quantity,
                )

            await self.session.commit()
        except Exception as exc:
            logger.error(
                "[OrderService] Position 同步失败 order_id=%d: %s",
                order.id,
                exc,
            )
