"""
订单 API — 使用统一交易 Schema
"""
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
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


class CreateExchangeAccountRequest(BaseModel):
    """创建交易所账户请求"""
    exchange: Literal["binance", "okx", "huobi"] = Field(description="交易所 (binance/okx/huobi)")
    account_name: str = Field(min_length=1, max_length=100, description="账户别名")
    api_key: str = Field(min_length=8, description="API Key")
    secret_key: str = Field(min_length=8, description="Secret Key")
    passphrase: str | None = Field(default=None, description="Passphrase (OKX 必须)")
    is_testnet: bool = Field(default=False, description="是否使用测试网")
    is_demo: bool = Field(default=False, description="是否使用模拟盘")

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


# ============ 路由 ============

@router.get("/accounts", response_model=list[AccountInfoSchema])
async def get_accounts(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """获取用户的交易所账户"""
    service = OrderService(session)
    accounts = await service.get_user_accounts(current_user.id)
    return [AccountInfoSchema.from_model(a) for a in accounts]


@router.post("", response_model=OrderSchema, status_code=status.HTTP_201_CREATED)
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
    return OrderSchema.from_model(order)


@router.get("", response_model=list[OrderSchema])
async def get_orders(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    account_id: int | None = None,
    symbol: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    """获取订单历史"""
    service = OrderService(session)
    orders = await service.get_order_history(
        user_id=current_user.id,
        account_id=account_id,
        symbol=symbol,
        limit=limit,
    )
    return [OrderSchema.from_model(o) for o in orders]


@router.post("/{order_id}/cancel", response_model=OrderSchema)
async def cancel_order(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """取消订单"""
    service = OrderService(session)
    order = await service.cancel_order(order_id, current_user.id)
    return OrderSchema.from_model(order)


@router.get("/positions", response_model=list[PositionSchema])
async def get_positions(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    account_id: int | None = None,
):
    """获取持仓"""
    service = OrderService(session)
    positions = await service.get_open_positions(current_user.id, account_id)
    return [PositionSchema.from_model(p) for p in positions]


@router.post("/{position_id}/stop-loss", response_model=PositionSchema)
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
    return PositionSchema.from_model(position)


@router.post("/{position_id}/take-profit", response_model=PositionSchema)
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
    return PositionSchema.from_model(position)


@router.post("/{position_id}/close", response_model=PositionSchema)
async def close_position(
    position_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """平仓"""
    service = OrderService(session)
    position = await service.close_position(position_id, current_user.id)
    return PositionSchema.from_model(position)


@router.post("/emergency-close-all")
async def emergency_close_all(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    account_id: int | None = None,
):
    """紧急一键平仓"""
    service = OrderService(session)
    closed = await service.emergency_close_all(current_user.id, account_id)
    return {
        "message": f"已平仓 {len(closed)} 个仓位",
        "closed_count": len(closed),
    }


# ============ 交易所账户管理 ============

@router.post("/accounts", response_model=AccountInfoSchema, status_code=status.HTTP_201_CREATED)
async def create_exchange_account(
    request: CreateExchangeAccountRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """添加交易所账户（API Key 加密存储）"""
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
    return AccountInfoSchema.from_model(account)


@router.delete("/accounts/{account_id}")
async def delete_exchange_account(
    account_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """删除交易所账户"""
    from sqlalchemy import select

    result = await session.execute(
        select(ExchangeAccount).where(
            ExchangeAccount.id == account_id,
            ExchangeAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="账户不存在")

    await session.delete(account)
    await session.commit()
    return {"message": "账户已删除"}
