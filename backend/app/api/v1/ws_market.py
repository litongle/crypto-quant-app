"""
WebSocket 行情推送模块 - 兼容层

P1-7: 该文件已拆分为 app.api.v1.ws 模块。
为了保持向后兼容，此处保留导出。
"""

from app.api.v1.ws.endpoints import cleanup_ws_proxies, init_ws_proxies, router
from app.api.v1.ws.manager import WSConnectionManager, manager
from app.api.v1.ws.proxies import BinanceWSProxy, ExchangeWSProxy, HuobiProxy, OKXProxy

__all__ = [
    "BinanceWSProxy",
    "ExchangeWSProxy",
    "HuobiProxy",
    "OKXProxy",
    "WSConnectionManager",
    "cleanup_ws_proxies",
    "init_ws_proxies",
    "manager",
    "router",
]
