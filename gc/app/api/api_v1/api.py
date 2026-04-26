"""
RSI分层极值追踪自动量化交易系统 - API路由主文件

该模块定义了系统的API路由结构，包括：
- 账户管理路由：管理交易账户、API密钥等
- 策略管理路由：RSI分层极值追踪策略的配置和管理
- 交易管理路由：订单、持仓和交易历史
- 数据查询路由：K线数据、技术指标等
- 系统管理路由：系统配置、日志、备份等
"""

from fastapi import APIRouter

from app.api.api_v1.endpoints import (
    accounts,
    strategies,
    trades,
    data,
    system,
    auth,
    dashboard,
    websocket
)

# 创建主路由器
api_router = APIRouter()

# 包含各个子模块的路由
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["认证"]
)

api_router.include_router(
    dashboard.router,
    prefix="/dashboard",
    tags=["仪表盘"]
)

api_router.include_router(
    accounts.router,
    prefix="/accounts",
    tags=["账户管理"]
)

api_router.include_router(
    strategies.router,
    prefix="/strategies",
    tags=["策略管理"]
)

api_router.include_router(
    trades.router,
    prefix="/trades",
    tags=["交易管理"]
)

api_router.include_router(
    data.router,
    prefix="/data",
    tags=["数据查询"]
)

api_router.include_router(
    system.router,
    prefix="/system",
    tags=["系统管理"]
)

# WebSocket路由单独处理，因为它们使用不同的协议
# websocket.router 在 app/main.py 中单独注册
