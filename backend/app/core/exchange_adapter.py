"""
交易所适配器 - 兼容层

P1-7: 该文件已拆分为 app.core.exchanges 模块。
为了保持向后兼容，此处保留导出。
"""
from app.core.exchanges import (
    BaseExchangeAdapter,
    BinanceAdapter,
    OKXAdapter,
    HuobiAdapter,
    get_exchange_adapter,
    Ticker,
    Kline,
    OrderBook,
    Balance,
    OrderResult,
    PositionInfo,
)
from app.core.exchanges.base import _safe_decimal, _safe_divide
