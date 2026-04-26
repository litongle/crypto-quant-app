"""
WebSocket 行情推送模块 - 兼容层

P1-7: 该文件已拆分为 app.api.v1.ws 模块。
为了保持向后兼容，此处保留导出。
"""
from app.api.v1.ws import (
    WSConnectionManager,
    manager,
    ExchangeWSProxy,
    BinanceWSProxy,
    OKXProxy as OKXWSProxy,
    HuobiProxy as HuobiWSProxy,
    router,
    init_ws_proxies,
    cleanup_ws_proxies,
)
