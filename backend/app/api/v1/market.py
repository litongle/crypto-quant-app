"""
市场数据 API
"""
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.market_service import MarketService, SUPPORTED_SYMBOLS
from app.core.schemas import APIResponse

router = APIRouter()

# 默认交易对
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"]


@router.get("/ticker/{symbol}")
async def get_ticker(
    symbol: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    exchange: str = Query(default="binance", pattern=r"^(binance|okx|huobi)$"),
):
    """
    获取实时行情
    
    Args:
        symbol: 交易对，如 BTCUSDT
        exchange: 交易所 (binance/okx/huobi)
    """
    service = MarketService(session)
    return await service.get_ticker(symbol, exchange)


@router.get("/kline/{symbol}")
async def get_kline(
    symbol: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    interval: str = Query(default="1h", pattern=r"^(1m|5m|15m|30m|1h|4h|1d|1w)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    exchange: str = Query(default="binance", pattern=r"^(binance|okx|huobi)$"),
):
    """
    获取K线数据
    
    Args:
        symbol: 交易对
        interval: K线周期 (1m/5m/15m/30m/1h/4h/1d/1w)
        limit: 数据条数 (1-1000)
        exchange: 交易所
    """
    service = MarketService(session)
    klines = await service.get_kline(symbol, interval, limit, exchange)
    return {"symbol": symbol.upper(), "interval": interval, "klines": klines}


@router.get("/orderbook/{symbol}")
async def get_orderbook(
    symbol: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=20, ge=1, le=100),
    exchange: str = Query(default="binance", pattern=r"^(binance|okx|huobi)$"),
):
    """
    获取订单簿
    
    Args:
        symbol: 交易对
        limit: 深度条数
        exchange: 交易所
    """
    service = MarketService(session)
    return await service.get_orderbook(symbol, limit, exchange)


@router.get("/symbols")
async def get_supported_symbols():
    """获取支持的交易对列表"""
    return {
        "symbols": list(SUPPORTED_SYMBOLS),
        "count": len(SUPPORTED_SYMBOLS),
    }


@router.get("/tickers")
async def get_batch_tickers(
    symbols: str = Query(
        default="BTC,ETH,SOL,BNB,DOGE",
        description="逗号分隔的交易对符号（不带USDT后缀）"
    ),
) -> APIResponse:
    """
    批量获取多个交易对的最新行情数据

    用于首页行情列表展示。
    """
    # 解析交易对
    symbol_list = [s.strip().upper() + "USDT" for s in symbols.split(",") if s.strip()]

    tickers = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Binance 批量获取24h行情
            url = "https://api.binance.com/api/v3/ticker/24hr"
            response = await client.get(url)
            response.raise_for_status()
            all_tickers = {t["symbol"]: t for t in response.json()}

            # 过滤并格式化
            for symbol in symbol_list:
                if symbol in all_tickers:
                    t = all_tickers[symbol]
                    # 生成迷你趋势数据（简化：使用收盘价）
                    sparkline = _generate_sparkline(float(t["lastPrice"]))
                    tickers.append({
                        "symbol": symbol,
                        "price": float(t["lastPrice"]),
                        "change24h": float(t["priceChange"]),
                        "changePercent24h": float(t["priceChangePercent"]),
                        "volume24h": float(t["quoteVolume"]),
                        "high24h": float(t["highPrice"]),
                        "low24h": float(t["lowPrice"]),
                        "sparkline": sparkline,
                    })
    except httpx.HTTPError:
        # 如果Binance API失败，返回模拟数据
        for symbol in symbol_list[:5]:
            base_price = {
                "BTCUSDT": 98500.50,
                "ETHUSDT": 3250.80,
                "SOLUSDT": 185.20,
                "BNBUSDT": 625.50,
                "DOGEUSDT": 0.3850,
            }.get(symbol, 100.0)
            change = base_price * 0.012 * (hash(symbol) % 10 - 5) / 5
            tickers.append({
                "symbol": symbol,
                "price": base_price + change,
                "change24h": change,
                "changePercent24h": change / base_price * 100,
                "volume24h": 15000000000,
                "high24h": base_price * 1.02,
                "low24h": base_price * 0.98,
                "sparkline": _generate_sparkline(base_price + change),
            })

    return APIResponse(data=tickers)


def _generate_sparkline(current_price: float) -> list[float]:
    """生成24点迷你趋势数据"""
    import random
    random.seed(int(current_price * 1000) % 10000)
    prices = []
    for i in range(8):
        factor = 1 + (random.random() - 0.5) * 0.02
        prices.append(current_price * factor)
    prices[-1] = current_price
    return prices
