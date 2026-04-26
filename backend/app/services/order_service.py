"""
订单服务
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

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
from app.models.strategy import StrategyInstance
from app.repositories.trading_repo import (
    ExchangeAccountRepository,
    PositionRepository,
    OrderRepository,
)
from app.repositories.strategy_repo import StrategyInstanceRepository

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

    async def sync_account_balance(self, account_id: int, user_id: int | None = None) -> ExchangeAccount:
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
            from app.core.exchange_adapter import get_exchange_adapter

            adapter = get_exchange_adapter(
                exchange=account.exchange,
                api_key=account.get_api_key(),
                secret_key=account.get_secret_key(),
                passphrase=account.get_passphrase() if account.encrypted_passphrase else None,
                testnet=account.is_testnet,
                is_demo=account.is_demo,
            )

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

            from datetime import datetime, timezone
            account.last_sync_at = datetime.now(timezone.utc)
            account.status = "active"
            account.error_message = None

            await self.session.commit()
            await self.session.refresh(account)

            logger.info(
                "[OrderService] 余额同步成功: account_id=%d, exchange=%s, "
                "balance=%.4f USDT, frozen=%.4f",
                account_id, account.exchange,
                float(account.balance), float(account.frozen_balance),
            )
            return account

        except Exception as exc:
            account.status = "error"
            account.error_message = f"余额同步失败: {str(exc)[:200]}"
            await self.session.commit()
            await self.session.refresh(account)

            logger.error(
                "[OrderService] 余额同步失败: account_id=%d, exchange=%s, error=%s",
                account_id, account.exchange, str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"余额同步失败: {str(exc)}",
            )

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
        )
        return await self.order_repo.create(order)

    async def submit_order(self, order_id: int, user_id: int) -> Order:
        """提交订单到交易所（真实下单）"""
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

        # 调用真实交易所 API
        try:
            from app.core.exchange_adapter import get_exchange_adapter

            adapter = get_exchange_adapter(
                exchange=account.exchange,
                api_key=account.get_api_key(),
                secret_key=account.get_secret_key(),
                passphrase=account.get_passphrase() if account.encrypted_passphrase else None,
                testnet=account.is_testnet,
                is_demo=account.is_demo,
            )

            logger.info(
                "[OrderService] 提交订单: order_id=%d, symbol=%s, side=%s, "
                "exchange=%s, demo=%s, testnet=%s",
                order_id, order.symbol, order.side,
                account.exchange, account.is_demo, account.is_testnet,
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
            order.submitted_at = datetime.now(timezone.utc)

            # 市价单直接用交易所返回值更新成交
            if result.filled_quantity > 0:
                order.filled_quantity = result.filled_quantity
                order.avg_fill_price = result.avg_fill_price
                if result.avg_fill_price and result.filled_quantity:
                    order.order_value = result.avg_fill_price * result.filled_quantity

            if result.status == "filled":
                order.filled_at = datetime.now(timezone.utc)

            logger.info(
                "[OrderService] 订单提交成功: order_id=%d, exchange_order_id=%s, status=%s",
                order_id, result.exchange_order_id, result.status,
            )

            await self.session.commit()
            await self.session.refresh(order)
            return order

        except OrderRejectedError as exc:
            # 交易所明确拒绝（余额不足/风控/参数错误）→ 标记 rejected
            order.status = "rejected"
            order.error_message = f"订单被拒: {exc.message}"
            await self.session.commit()
            await self.session.refresh(order)
            logger.warning(
                "[OrderService] 订单被拒: order_id=%d, exchange=%s, code=%s, msg=%s",
                order_id, exc.exchange, exc.detail_code, exc.message,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"订单被交易所拒绝: {exc.message}",
            )

        except RateLimitError as exc:
            # 限流 → 不改状态，让前端可重试
            logger.warning(
                "[OrderService] 交易所限流: order_id=%d, exchange=%s",
                order_id, exc.exchange,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"交易所请求频率超限，请稍后重试",
            )

        except NetworkError as exc:
            # 网络异常 → 标记 pending（可能已提交但未确认）
            order.error_message = f"网络异常: {exc.message}"
            await self.session.commit()
            await self.session.refresh(order)
            logger.error(
                "[OrderService] 网络异常: order_id=%d, exchange=%s, msg=%s",
                order_id, exc.exchange, exc.message,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"交易所网络异常，请检查订单状态: {exc.message}",
            )

        except ExchangeAPIError as exc:
            # 其他交易所错误 → 标记 rejected
            order.status = "rejected"
            order.error_message = f"交易所错误: {exc.message}"
            await self.session.commit()
            await self.session.refresh(order)
            logger.error(
                "[OrderService] 交易所API错误: order_id=%d, exchange=%s, code=%s, retryable=%s",
                order_id, exc.exchange, exc.detail_code, exc.retryable,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"交易所下单失败: {exc.message}",
            )

        except AppException:
            raise
        except Exception as e:
            order.status = "rejected"
            order.error_message = f"下单失败: {str(e)}"
            await self.session.commit()
            await self.session.refresh(order)
            logger.exception(
                "[OrderService] 下单未知异常: order_id=%d", order_id,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"交易所下单失败: {str(e)}",
            )

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
                from app.core.exchange_adapter import get_exchange_adapter

                adapter = get_exchange_adapter(
                    exchange=account.exchange,
                    api_key=account.get_api_key(),
                    secret_key=account.get_secret_key(),
                    passphrase=account.get_passphrase() if account.encrypted_passphrase else None,
                    testnet=account.is_testnet,
                    is_demo=account.is_demo,
                )

                logger.info(
                    "[OrderService] 撤单: order_id=%d, exchange_order_id=%s, symbol=%s",
                    order_id, order.exchange_order_id, order.symbol,
                )

                success = await adapter.cancel_order(order.exchange_order_id, order.symbol)
                if not success:
                    logger.warning(
                        "[OrderService] 撤单未成功: order_id=%d, exchange_order_id=%s",
                        order_id, order.exchange_order_id,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="交易所撤单失败",
                    )
            except OrderRejectedError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"撤单被拒: {exc.message}",
                )
            except RateLimitError as exc:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="交易所请求频率超限，请稍后重试",
                )
            except NetworkError as exc:
                logger.error(
                    "[OrderService] 撤单网络异常: order_id=%d, msg=%s",
                    order_id, exc.message,
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"交易所网络异常: {exc.message}",
                )
            except ExchangeAPIError as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"交易所撤单失败: {exc.message}",
                )
            except AppException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"交易所撤单失败: {str(e)}",
                )

        order.status = "cancelled"
        order.cancelled_at = datetime.now(timezone.utc)
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

        # 只有交易所确认成功后才标记平仓
        position.status = "closed"
        position.closed_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(position)
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

    async def set_stop_loss(
        self, position_id: int, user_id: int, stop_price: Decimal
    ) -> Position:
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
            from app.core.exchange_adapter import get_exchange_adapter

            adapter = get_exchange_adapter(
                exchange=account.exchange,
                api_key=account.get_api_key(),
                secret_key=account.get_secret_key(),
                passphrase=account.get_passphrase() if account.encrypted_passphrase else None,
                testnet=account.is_testnet,
                is_demo=account.is_demo,
            )

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
                position_id, position.symbol, stop_price, result.exchange_order_id,
            )

        except Exception as exc:
            # 条件单提交失败时仍保存本地止损价（降级模式）
            logger.warning(
                "[OrderService] 止损条件单提交失败，降级为本地止损: position_id=%d, error=%s",
                position_id, str(exc),
            )

        position.stop_loss_price = stop_price
        await self.session.commit()
        await self.session.refresh(position)
        return position

    async def set_take_profit(
        self, position_id: int, user_id: int, tp_price: Decimal
    ) -> Position:
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
            from app.core.exchange_adapter import get_exchange_adapter

            adapter = get_exchange_adapter(
                exchange=account.exchange,
                api_key=account.get_api_key(),
                secret_key=account.get_secret_key(),
                passphrase=account.get_passphrase() if account.encrypted_passphrase else None,
                testnet=account.is_testnet,
                is_demo=account.is_demo,
            )

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
                position_id, position.symbol, tp_price, result.exchange_order_id,
            )

        except Exception as exc:
            # 条件单提交失败时仍保存本地止盈价（降级模式）
            logger.warning(
                "[OrderService] 止盈条件单提交失败，降级为本地止盈: position_id=%d, error=%s",
                position_id, str(exc),
            )

        position.take_profit_price = tp_price
        await self.session.commit()
        await self.session.refresh(position)
        return position
