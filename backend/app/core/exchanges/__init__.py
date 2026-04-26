"""
交易所适配器模块
"""
import logging
from .base import (
    BaseExchangeAdapter,
    Ticker,
    Kline,
    OrderBook,
    Balance,
    OrderResult,
    PositionInfo,
)
from .binance import BinanceAdapter
from .okx import OKXAdapter
from .huobi import HuobiAdapter

logger = logging.getLogger(__name__)

def get_exchange_adapter(
    exchange: str,
    api_key: str,
    secret_key: str,
    passphrase: str | None = None,
    testnet: bool = False,
    is_demo: bool = False,
) -> BaseExchangeAdapter:
    """获取交易所适配器工厂函数"""
    exchange_lower = exchange.lower()
    
    if exchange_lower == "binance":
        return BinanceAdapter(api_key, secret_key, passphrase, testnet=testnet)
    elif exchange_lower == "okx":
        return OKXAdapter(api_key, secret_key, passphrase, is_demo=is_demo)
    elif exchange_lower in ("huobi", "htx"):
        return HuobiAdapter(api_key, secret_key, passphrase)
    else:
        raise ValueError(f"不支持的交易所: {exchange}")
