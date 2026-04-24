"""API v1 Router"""
from fastapi import APIRouter

from app.api.v1 import auth, strategies, users, market, orders, asset, backtest, setup, ws_market

api_router = APIRouter()

# 安装向导（无需认证）
api_router.include_router(setup.router, prefix="/setup", tags=["安装向导"])

# 认证
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])

# 用户
api_router.include_router(users.router, prefix="/users", tags=["用户"])

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

# WebSocket 行情推送（不走 /api/v1 前缀，直接 /ws/）
api_router.include_router(ws_market.router, prefix="/ws", tags=["WebSocket"])
