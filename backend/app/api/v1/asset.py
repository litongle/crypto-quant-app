"""
资产相关 API 路由
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.api.deps import get_current_user
from app.core.schemas import APIResponse
from app.services.asset_service import AssetService

router = APIRouter()


@router.get("/summary")
async def get_asset_summary(
    exchange: str = Query("all", description="交易所筛选 (binance/okx/htx/all)"),
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """
    获取资产汇总

    返回用户聚合后的总资产信息，包括总资产、累计盈亏、可用余额、冻结余额。
    """
    service = AssetService(session)
    data = await service.get_asset_summary(
        user_id=current_user.id,
        exchange=exchange,
    )
    return APIResponse(data=data)


@router.get("/positions")
async def get_positions(
    exchange: str = Query("all", description="交易所筛选"),
    side: str = Query("all", description="方向筛选 (long/short/all)"),
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """
    获取持仓列表

    返回用户当前所有持仓，包括现货和合约持仓。
    """
    service = AssetService(session)
    data = await service.get_positions(
        user_id=current_user.id,
        exchange=exchange,
        side=side,
    )
    return APIResponse(data=data)


@router.get("/equity-curve")
async def get_equity_curve(
    days: int = Query(30, description="查询天数 (7/30/90/180/365)", ge=7, le=365),
    exchange: str = Query("all", description="交易所筛选"),
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """
    获取权益曲线数据

    返回账户权益曲线历史数据及统计指标。
    """
    service = AssetService(session)
    data = await service.get_equity_curve(
        user_id=current_user.id,
        days=days,
        exchange=exchange,
    )
    return APIResponse(data=data)
