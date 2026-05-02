"""
交易所适配器模块
"""

from .base import (
    Balance as Balance,
)
from .base import (
    BaseExchangeAdapter as BaseExchangeAdapter,
)
from .base import (
    Kline as Kline,
)
from .base import (
    OrderBook as OrderBook,
)
from .base import (
    OrderResult as OrderResult,
)
from .base import (
    PositionInfo as PositionInfo,
)
from .base import (
    SymbolInfo as SymbolInfo,
)
from .base import (
    Ticker as Ticker,
)
from .binance import BinanceAdapter as BinanceAdapter
from .huobi import HuobiAdapter as HuobiAdapter
from .okx import OKXAdapter as OKXAdapter


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
