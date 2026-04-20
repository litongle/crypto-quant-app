"""
订单 API
"""
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.user import User
from app.api.deps import get_current_user
from app.services.order_service import OrderService

router = APIRouter()


# ============ 请求模型 ============

class CreateOrderRequest(BaseModel):
    """创建订单请求"""
    account_id: int = Field(gt=0, description="账户ID必须为正整数")
    symbol: str = Field(pattern=r"^[A-Z]{2,10}(USDT|USDC|BTC|ETH)?$")
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    quantity: Decimal = Field(gt=0, decimal_places=8, description="数量必须大于0")
    price: Decimal | None = Field(default=None, gt=0, decimal_places=8, description="限价单价格必须大于0")
    strategy_instance_id: int | None = Field(default=None, gt=0)


class SetStopLossRequest(BaseModel):
    """设置止损请求"""
    account_id: int = Field(gt=0)
    stop_price: Decimal = Field(gt=0, description="止损价格必须大于0")


class SetTakeProfitRequest(BaseModel):
    """设置止盈请求"""
    account_id: int = Field(gt=0)
    take_profit_price: Decimal = Field(gt=0, description="止盈价格必须大于0")


# ============ 响应模型 ============

class AccountResponse(BaseModel):
    """账户响应"""
    id: int
    exchange: str
    account_name: str
    is_active: bool
    status: str

    class Config:
        from_attributes = True


class PositionResponse(BaseModel):
    """持仓响应"""
    id: int
    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_percent: Decimal
    leverage: int
    stop_loss_price: Decimal | None
    take_profit_price: Decimal | None
    status: str

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    """订单响应"""
    id: int
    symbol: str
    side: str
    order_type: str
    quantity: Decimal
    price: Decimal | None
    filled_quantity: Decimal
    avg_fill_price: Decimal | None
    status: str
    created_at: str

    class Config:
        from_attributes = True


# ============ 路由 ============

@router.get("/accounts", response_model=list[AccountResponse])
async def get_accounts(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """获取用户的交易所账户"""
    service = OrderService(session)
    accounts = await service.get_user_accounts(current_user.id)
    return [AccountResponse.model_validate(a) for a in accounts]


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    request: CreateOrderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
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
    return OrderResponse.model_validate(order)


@router.get("", response_model=list[OrderResponse])
async def get_orders(
    current_user: Annotated[User, Depends(get_current_user)],
    account_id: int | None = None,
    symbol: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """获取订单历史"""
    service = OrderService(session)
    orders = await service.get_order_history(
        user_id=current_user.id,
        account_id=account_id,
        symbol=symbol,
        limit=limit,
    )
    return [OrderResponse.model_validate(o) for o in orders]


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """取消订单"""
    service = OrderService(session)
    order = await service.cancel_order(order_id, current_user.id)
    return OrderResponse.model_validate(order)


@router.get("/positions", response_model=list[PositionResponse])
async def get_positions(
    current_user: Annotated[User, Depends(get_current_user)],
    account_id: int | None = None,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """获取持仓"""
    service = OrderService(session)
    positions = await service.get_open_positions(current_user.id, account_id)
    return [PositionResponse.model_validate(p) for p in positions]


@router.post("/{position_id}/stop-loss", response_model=PositionResponse)
async def set_stop_loss(
    position_id: int,
    request: SetStopLossRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """设置止损"""
    service = OrderService(session)
    position = await service.set_stop_loss(
        position_id=position_id,
        user_id=current_user.id,
        stop_price=request.stop_price,
    )
    return PositionResponse.model_validate(position)


@router.post("/{position_id}/take-profit", response_model=PositionResponse)
async def set_take_profit(
    position_id: int,
    request: SetTakeProfitRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """设置止盈"""
    service = OrderService(session)
    position = await service.set_take_profit(
        position_id=position_id,
        user_id=current_user.id,
        tp_price=request.take_profit_price,
    )
    return PositionResponse.model_validate(position)


@router.post("/{position_id}/close", response_model=PositionResponse)
async def close_position(
    position_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """平仓"""
    service = OrderService(session)
    position = await service.close_position(position_id, current_user.id)
    return PositionResponse.model_validate(position)


@router.post("/emergency-close-all")
async def emergency_close_all(
    current_user: Annotated[User, Depends(get_current_user)],
    account_id: int | None = None,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """紧急一键平仓"""
    service = OrderService(session)
    closed = await service.emergency_close_all(current_user.id, account_id)
    return {
        "message": f"已平仓 {len(closed)} 个仓位",
        "closed_count": len(closed),
    }
