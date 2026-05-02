"""
交易所适配器 - 兼容层

P1-7: 该文件已拆分为 app.core.exchanges 模块。
为了保持向后兼容，此处保留导出。
"""

from app.core.exchanges import (
    Balance,
    BaseExchangeAdapter,
    BinanceAdapter,
    HuobiAdapter,
    Kline,
    OKXAdapter,
    OrderBook,
    OrderResult,
    PositionInfo,
    SymbolInfo,
    Ticker,
    get_exchange_adapter,
)

__all__ = [
    "Balance",
    "BaseExchangeAdapter",
    "BinanceAdapter",
    "HuobiAdapter",
    "Kline",
    "OKXAdapter",
    "OrderBook",
    "OrderResult",
    "PositionInfo",
    "SymbolInfo",
    "Ticker",
    "get_exchange_adapter",
]
