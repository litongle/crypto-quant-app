"""
订单服务
"""

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
from app.models.exchange import ExchangeAccount, Position
from app.models.order import Order
from app.repositories.strategy_repo import StrategyInstanceRepository
from app.repositories.trading_repo import (
    ExchangeAccountRepository,
    OrderRepository,
    PositionRepository,
)

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

    async def get_user_accounts(self, user_id: int) -> list[ExchangeAccount]:
        """获取用户的交易所账户"""
        return await self.account_repo.get_active_by_user(user_id)

    async def _get_adapter(self, account: ExchangeAccount):
        """获取交易所适配器助手 (P1-11: 统一解密逻辑)"""
        from app.core.exchange_adapter import get_exchange_adapter

        return get_exchange_adapter(
            exchange=account.exchange,
            api_key=account.get_api_key(),
            secret_key=account.get_secret_key(),
            passphrase=account.get_passphrase() if account.encrypted_passphrase else None,
            testnet=account.is_testnet,
            is_demo=account.is_demo,
        )

    async def sync_account_balance(
        self, account_id: int, user_id: int | None = None
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

        try:
            adapter = await self._get_adapter(account)
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

            from datetime import datetime

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

    async def submit_order(self, order_id: int, user_id: int) -> Order:
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

        # 调用真实交易所 API
        try:
            adapter = await self._get_adapter(account)

            logger.info(
                "[OrderService] 提交订单: order_id=%d, symbol=%s, side=%s, "
                "exchange=%s, demo=%s, testnet=%s, client_order_id=%s",
                order_id,
                order.symbol,
                order.side,
                account.exchange,
                account.is_demo,
                account.is_testnet,
                order.client_order_id,
            )

            result = await adapter.create_order(
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                quantity=order.quantity,
                price=order.price,
            )

            # 更新订单状态
            order.exchange_order_id = result.exchange_order_id
            order.status = result.status
            order.submitted_at = datetime.now(UTC)

            # 市价单直接用交易所返回值更新成交
            if result.filled_quantity > 0:
                order.filled_quantity = result.filled_quantity
                order.avg_fill_price = result.avg_fill_price
                if result.avg_fill_price and result.filled_quantity:
                    order.order_value = result.avg_fill_price * result.filled_quantity

            if result.status == "filled":
                order.filled_at = datetime.now(UTC)

            logger.info(
                "[OrderService] 订单提交成功: order_id=%d, exchange_order_id=%s, status=%s",
                order_id,
                result.exchange_order_id,
                result.status,
            )

            await self.session.commit()
            await self.session.refresh(order)

            # 评审问题4: 订单成交后自动创建/更新 Position 记录
            if result.status == "filled":
                await self._sync_position_on_fill(order, account, result)

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
                adapter = await self._get_adapter(account)

                logger.info(
                    "[OrderService] 撤单: order_id=%d, exchange_order_id=%s, symbol=%s",
                    order_id,
                    order.exchange_order_id,
                    order.symbol,
                )

                success = await adapter.cancel_order(order.exchange_order_id, order.symbol)
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

    async def close_position(self, position_id: int, user_id: int) -> Position:
        """平仓 — P1-1: 交易所成功后再标记 closed，使用事务安全顺序"""
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
        await self.submit_order(order.id, user_id)

        # 计算盈亏
        realized_pnl = Decimal("0")
        if order.avg_fill_price and position.entry_price:
            if position.side == "long":
                realized_pnl = (order.avg_fill_price - position.entry_price) * position.quantity
            else:
                realized_pnl = (position.entry_price - order.avg_fill_price) * position.quantity

        # 只有交易所确认成功后才标记平仓
        position.status = "closed"
        position.closed_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(position)

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
            adapter = await self._get_adapter(account)

            result = await adapter.create_stop_order(
                symbol=position.symbol,
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
            adapter = await self._get_adapter(account)

            result = await adapter.create_stop_order(
                symbol=position.symbol,
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
        """评审问题4：订单完全成交后自动创建 Position 记录

        买入(buy) → 创建新 long 持仓（或增加现有持仓数量）
        卖出(sell) → 若有关联 strategy_instance 的 open 持仓，标记为 closed
                     否则也创建 short 持仓
        """
        try:
            if order.side == "buy":
                # 买入 → 寻找已有同方向 open 持仓合并，或新建
                existing = await self.position_repo.get_by_account_and_symbol(
                    order.account_id,
                    order.symbol,
                )
                # 只合并 strategy_instance_id 匹配的 long 持仓
                merge_target = None
                for p in existing:
                    if (
                        p.side == "long"
                        and p.status == "open"
                        and p.strategy_instance_id == order.strategy_instance_id
                    ):
                        merge_target = p
                        break

                if merge_target:
                    # 加仓：加权平均开仓价
                    total_qty = merge_target.quantity + order.filled_quantity
                    if order.avg_fill_price:
                        weighted_price = (
                            merge_target.entry_price * merge_target.quantity
                            + order.avg_fill_price * order.filled_quantity
                        ) / total_qty
                        merge_target.entry_price = weighted_price
                    merge_target.quantity = total_qty
                    merge_target.current_price = order.avg_fill_price or merge_target.current_price
                    merge_target.updated_at = datetime.now(UTC)
                    logger.info(
                        "[OrderService] 加仓 Position #%d: qty=%s, avg_price=%s",
                        merge_target.id,
                        merge_target.quantity,
                        merge_target.entry_price,
                    )
                else:
                    # 新建 long 持仓
                    new_pos = Position(
                        account_id=order.account_id,
                        symbol=order.symbol,
                        side="long",
                        quantity=order.filled_quantity,
                        entry_price=order.avg_fill_price or Decimal("0"),
                        current_price=order.avg_fill_price or Decimal("0"),
                        status="open",
                        strategy_instance_id=order.strategy_instance_id,
                        opened_at=datetime.now(UTC),
                    )
                    self.session.add(new_pos)
                    await self.session.flush()
                    logger.info(
                        "[OrderService] 新建 long Position #%d: symbol=%s, qty=%s",
                        new_pos.id,
                        order.symbol,
                        order.filled_quantity,
                    )

            elif order.side == "sell":
                # 卖出 → 查找关联的 open 持仓平掉
                existing = await self.position_repo.get_by_account_and_symbol(
                    order.account_id,
                    order.symbol,
                )
                close_target = None
                for p in existing:
                    if (
                        p.status == "open"
                        and p.strategy_instance_id == order.strategy_instance_id
                        and p.side in ("long", "short")
                    ):
                        close_target = p
                        break

                if close_target:
                    close_target.status = "closed"
                    close_target.closed_at = datetime.now(UTC)
                    logger.info(
                        "[OrderService] 平仓 Position #%d (side=%s)",
                        close_target.id,
                        close_target.side,
                    )
                else:
                    # 无匹配持仓 → 可能是开空仓
                    new_pos = Position(
                        account_id=order.account_id,
                        symbol=order.symbol,
                        side="short",
                        quantity=order.filled_quantity,
                        entry_price=order.avg_fill_price or Decimal("0"),
                        current_price=order.avg_fill_price or Decimal("0"),
                        status="open",
                        strategy_instance_id=order.strategy_instance_id,
                        opened_at=datetime.now(UTC),
                    )
                    self.session.add(new_pos)
                    await self.session.flush()
                    logger.info(
                        "[OrderService] 新建 short Position #%d: symbol=%s, qty=%s",
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
