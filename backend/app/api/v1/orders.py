"""
订单 API — 统一 APIResponse + IDOR 修复 + 一键平仓确认

路由排列规则：静态路径优先，参数化路径靠后，避免 FastAPI 路由冲突
"""
import logging
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.user import User
from app.models.exchange import ExchangeAccount
from app.api.deps import get_current_user
from app.services.order_service import OrderService
from app.core.trade_schemas import (
    AccountInfoSchema,
    OrderSchema,
    PositionSchema,
)
from app.core.schemas import APIResponse

logger = logging.getLogger(__name__)


class CreateExchangeAccountRequest(BaseModel):
    """创建交易所账户请求"""
    exchange: Literal["binance", "okx", "huobi"] = Field(description="交易所 (binance/okx/huobi)")
    account_name: str = Field(min_length=1, max_length=100, description="账户别名")
    api_key: str = Field(min_length=8, description="API Key")
    secret_key: str = Field(min_length=8, description="Secret Key")
    passphrase: str | None = Field(default=None, description="Passphrase (OKX 必须)")
    is_testnet: bool = Field(default=False, description="是否使用测试网")
    is_demo: bool = Field(default=False, description="是否使用模拟盘")

    def model_post_init(self, __context: object) -> None:
        """OKX 必须提供 passphrase"""
        if self.exchange == "okx" and not self.passphrase:
            raise ValueError("OKX 交易所必须提供 Passphrase（创建 API Key 时设置的口令）")


router = APIRouter()


# ============ 请求模型 ============

class CreateOrderRequest(BaseModel):
    """创建订单请求"""
    account_id: int = Field(gt=0, description="账户ID必须为正整数")
    symbol: str = Field(pattern=r"^[A-Z]{2,10}(USDT|USDC|BTC|ETH)?$")
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    quantity: Decimal = Field(gt=0, description="数量必须大于0")
    price: Decimal | None = Field(default=None, gt=0, description="限价单价格必须大于0")
    strategy_instance_id: int | None = Field(default=None, gt=0)


class SetStopLossRequest(BaseModel):
    """设置止损请求"""
    account_id: int = Field(gt=0)
    stop_price: Decimal = Field(gt=0, description="止损价格必须大于0")


class SetTakeProfitRequest(BaseModel):
    """设置止盈请求"""
    account_id: int = Field(gt=0)
    take_profit_price: Decimal = Field(gt=0, description="止盈价格必须大于0")


class EmergencyCloseConfirm(BaseModel):
    """一键平仓确认请求"""
    confirm: bool = Field(..., description="必须传 confirm=true 才会执行平仓")
    account_id: int | None = Field(default=None, description="指定账户ID，不传则平所有账户")


# ============================================================
# 交易所账户管理（静态路径优先注册，避免被 /{id} 路由拦截）
# ============================================================

@router.get("/accounts")
async def get_accounts(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """获取用户的交易所账户"""
    service = OrderService(session)
    accounts = await service.get_user_accounts(current_user.id)
    return APIResponse(data=[AccountInfoSchema.from_model(a).model_dump() for a in accounts])


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_exchange_account(
    request: CreateExchangeAccountRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """添加交易所账户（API Key 加密存储 + 自动同步余额）"""
    account = ExchangeAccount(
        user_id=current_user.id,
        exchange=request.exchange,
        account_name=request.account_name,
        is_testnet=request.is_testnet,
        is_demo=request.is_demo,
        is_active=True,
        status="active",
    )
    # 加密存储敏感信息
    account.set_api_key(request.api_key)
    account.set_secret_key(request.secret_key)
    if request.passphrase:
        account.set_passphrase(request.passphrase)

    session.add(account)
    await session.commit()
    await session.refresh(account)

    # 创建后自动从交易所同步余额
    try:
        service = OrderService(session)
        account = await service.sync_account_balance(account.id, current_user.id)
    except Exception as exc:
        logger.warning("[create_exchange_account] 余额同步失败（账户已创建）: %s", exc)

    return APIResponse(data=AccountInfoSchema.from_model(account).model_dump())


@router.post("/accounts/{account_id}/sync")
async def sync_account_balance(
    account_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """手动同步交易所账户余额"""
    # IDOR 修复：验证账户所有权
    result = await session.execute(
        select(ExchangeAccount).where(
            ExchangeAccount.id == account_id,
            ExchangeAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在或无权操作")

    service = OrderService(session)
    account = await service.sync_account_balance(account_id, current_user.id)
    return APIResponse(data=AccountInfoSchema.from_model(account).model_dump())


@router.delete("/accounts/{account_id}")
async def delete_exchange_account(
    account_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """删除交易所账户"""
    result = await session.execute(
        select(ExchangeAccount).where(
            ExchangeAccount.id == account_id,
            ExchangeAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")

    await session.delete(account)
    await session.commit()
    return APIResponse(message="账户已删除")


# ============================================================
# 交易操作（静态路径优先）
# ============================================================

@router.post("/emergency-close-all")
async def emergency_close_all(
    request: EmergencyCloseConfirm,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """紧急一键平仓（需 confirm=true 确认）"""
    if not request.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请确认操作：必须传 confirm=true",
        )

    service = OrderService(session)
    closed = await service.emergency_close_all(current_user.id, request.account_id)
    return APIResponse(data={
        "closed_count": len(closed),
        "message": f"已平仓 {len(closed)} 个仓位",
    })


@router.get("/positions")
async def get_positions(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    account_id: int | None = None,
) -> APIResponse:
    """获取持仓"""
    service = OrderService(session)
    positions = await service.get_open_positions(current_user.id, account_id)
    return APIResponse(data=[PositionSchema.from_model(p).model_dump() for p in positions])


# ============================================================
# 订单 CRUD（参数化路径放最后）
# ============================================================

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(
    request: CreateOrderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """创建订单"""
    service = OrderService(session)

    # 格式化交易对
    symbol = request.symbol.upper()
    if not symbol.endswith(("USDT", "USDC", "BTC", "ETH")):
        symbol += "USDT"

    order = await service.create_order(
        user_id=current_user.id,
        account_id=request.account_id,
        symbol=symbol,
        side=request.side,
        order_type=request.order_type,
        quantity=request.quantity,
        price=request.price,
        strategy_instance_id=request.strategy_instance_id,
    )

    # 提交订单
    order = await service.submit_order(order.id, current_user.id)
    return APIResponse(data=OrderSchema.from_model(order).model_dump())


@router.get("")
async def get_orders(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    account_id: int | None = None,
    symbol: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> APIResponse:
    """获取订单历史"""
    service = OrderService(session)
    orders = await service.get_order_history(
        user_id=current_user.id,
        account_id=account_id,
        symbol=symbol,
        limit=limit,
    )
    return APIResponse(data=[OrderSchema.from_model(o).model_dump() for o in orders])


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """取消订单"""
    service = OrderService(session)
    order = await service.cancel_order(order_id, current_user.id)
    return APIResponse(data=OrderSchema.from_model(order).model_dump())


@router.post("/{position_id}/stop-loss")
async def set_stop_loss(
    position_id: int,
    request: SetStopLossRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """设置止损"""
    service = OrderService(session)
    position = await service.set_stop_loss(
        position_id=position_id,
        user_id=current_user.id,
        stop_price=request.stop_price,
    )
    return APIResponse(data=PositionSchema.from_model(position).model_dump())


@router.post("/{position_id}/take-profit")
async def set_take_profit(
    position_id: int,
    request: SetTakeProfitRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """设置止盈"""
    service = OrderService(session)
    position = await service.set_take_profit(
        position_id=position_id,
        user_id=current_user.id,
        tp_price=request.take_profit_price,
    )
    return APIResponse(data=PositionSchema.from_model(position).model_dump())


@router.post("/{position_id}/close")
async def close_position(
    position_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """平仓"""
    service = OrderService(session)
    position = await service.close_position(position_id, current_user.id)
    return APIResponse(data=PositionSchema.from_model(position).model_dump())
