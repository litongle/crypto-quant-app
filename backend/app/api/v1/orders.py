"""交易账户与持仓 API。"""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.schemas import APIResponse
from app.core.trade_schemas import (
    AccountInfoSchema,
    PositionSchema,
    TradingSymbolRulesSchema,
)
from app.database import get_session
from app.models.exchange import ExchangeAccount
from app.models.user import User
from app.services.order_service import OrderService

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


class UpdateContractSettingsRequest(BaseModel):
    """更新合约参数请求"""

    symbol: str = Field(pattern=r"^[A-Z]{2,10}(USDT|USDC|BTC|ETH)?(?:\.P)?$")
    leverage: int = Field(ge=1, le=125)
    margin_mode: Literal["cross", "isolated"] = Field(alias="marginMode")


# ============================================================
# 交易所账户管理（静态路径优先注册，避免被 /{id} 路由拦截）
# ============================================================


@router.get("/accounts")
async def get_accounts(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    include_paper: bool = Query(default=False),
) -> APIResponse:
    """获取用户的交易所账户"""
    service = OrderService(session)
    accounts = await service.get_user_accounts(current_user.id, include_paper=include_paper)
    return APIResponse(
        data=[AccountInfoSchema.from_model(a).model_dump(by_alias=True) for a in accounts]
    )


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

    return APIResponse(data=AccountInfoSchema.from_model(account).model_dump(by_alias=True))


@router.get("/accounts/{account_id}")
async def get_account(
    account_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """获取指定交易所账户详情"""
    result = await session.execute(
        select(ExchangeAccount).where(
            ExchangeAccount.id == account_id,
            ExchangeAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在或无权操作")
    return APIResponse(data=AccountInfoSchema.from_model(account).model_dump(by_alias=True))


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
    await session.commit()
    return APIResponse(data=AccountInfoSchema.from_model(account).model_dump(by_alias=True))


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
# 持仓与账户配置（静态路径优先）
# ============================================================


@router.get("/positions")
async def get_positions(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    account_id: int | None = None,
) -> APIResponse:
    """获取持仓"""
    service = OrderService(session)
    positions = await service.get_open_positions(current_user.id, account_id)
    return APIResponse(
        data=[PositionSchema.from_model(p).model_dump(by_alias=True) for p in positions]
    )


@router.get("/symbol-rules")
async def get_trading_symbol_rules(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    account_id: int = Query(..., gt=0),
    symbol: str = Query(..., pattern=r"^[A-Z]{2,10}(USDT|USDC|BTC|ETH)?(?:\.P)?$"),
) -> APIResponse[TradingSymbolRulesSchema]:
    """获取交易规则与市场语义。"""
    service = OrderService(session)
    rules = await service.get_symbol_rules(
        user_id=current_user.id,
        account_id=account_id,
        symbol=symbol,
    )
    return APIResponse(data=rules.model_dump(by_alias=True))


@router.get("/accounts/{account_id}/contract-settings")
async def get_contract_settings(
    account_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    symbol: str = Query(..., pattern=r"^[A-Z]{2,10}(USDT|USDC|BTC|ETH)?(?:\.P)?$"),
) -> APIResponse:
    """获取合约杠杆与保证金模式设置"""
    service = OrderService(session)
    data = await service.get_contract_settings(
        user_id=current_user.id,
        account_id=account_id,
        symbol=symbol,
    )
    return APIResponse(data=data)


@router.post("/accounts/{account_id}/contract-settings")
async def update_contract_settings(
    account_id: int,
    request: UpdateContractSettingsRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """更新合约杠杆与保证金模式设置"""
    service = OrderService(session)
    data = await service.update_contract_settings(
        user_id=current_user.id,
        account_id=account_id,
        symbol=request.symbol,
        leverage=request.leverage,
        margin_mode=request.margin_mode,
    )
    await session.commit()
    return APIResponse(data=data)
