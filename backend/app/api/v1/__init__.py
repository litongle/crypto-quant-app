"""API v1 Router"""

from fastapi import APIRouter

from app.api.v1 import (
    asset,
    auth,
    backtest,
    events,
    market,
    orders,
    settings,
    strategies,
    ws,
)

api_router = APIRouter()

# 认证
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])

# 策略
api_router.include_router(strategies.router, prefix="/strategies", tags=["策略"])

# 回测
api_router.include_router(backtest.router, prefix="/backtest", tags=["回测"])

# 市场数据
api_router.include_router(market.router, prefix="/market", tags=["行情"])

# 资产
api_router.include_router(asset.router, prefix="/asset", tags=["资产"])

# 交易/订单
api_router.include_router(orders.router, prefix="/trading", tags=["交易"])

# 事件流
api_router.include_router(events.router, prefix="/events", tags=["事件"])

# 运行时设置（通知通道 / SMTP / 风控阈值）
api_router.include_router(settings.router)

# WebSocket 行情推送（不走 /api/v1 前缀，直接 /ws/）
api_router.include_router(ws.router, prefix="/ws", tags=["WebSocket"])
