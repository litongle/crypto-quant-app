"""
市场数据 API — 统一 APIResponse 响应格式
"""
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query

from app.services.market_service import MarketService, SUPPORTED_SYMBOLS
from app.core.schemas import APIResponse
from app.api.deps import DbSession

router = APIRouter()

# 默认交易对
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"]


@router.get("/ticker/{symbol}")
async def get_ticker(
    symbol: str,
    session: DbSession,
    exchange: str = Query(default="binance", pattern=r"^(binance|okx|huobi)$"),
) -> APIResponse:
    """
    获取实时行情

    Args:
        symbol: 交易对，如 BTCUSDT
        exchange: 交易所 (binance/okx/huobi)
    """
    service = MarketService(session)
    data = await service.get_ticker(symbol, exchange)
    return APIResponse(data=data)


@router.get("/kline/{symbol}")
async def get_kline(
    symbol: str,
    session: DbSession,
    interval: str = Query(default="1h", pattern=r"^(1m|5m|15m|30m|1h|4h|1d|1w)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    exchange: str = Query(default="binance", pattern=r"^(binance|okx|huobi)$"),
) -> APIResponse:
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
    return APIResponse(data={"symbol": symbol.upper(), "interval": interval, "klines": klines})


@router.get("/orderbook/{symbol}")
async def get_orderbook(
    symbol: str,
    session: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
    exchange: str = Query(default="binance", pattern=r"^(binance|okx|huobi)$"),
) -> APIResponse:
    """
    获取订单簿

    Args:
        symbol: 交易对
        limit: 深度条数
        exchange: 交易所
    """
    service = MarketService(session)
    data = await service.get_orderbook(symbol, limit, exchange)
    return APIResponse(data=data)


@router.get("/symbols")
async def get_supported_symbols() -> APIResponse:
    """获取支持的交易对列表"""
    return APIResponse(data={
        "symbols": list(SUPPORTED_SYMBOLS),
        "count": len(SUPPORTED_SYMBOLS),
    })


@router.get("/tickers")
async def get_batch_tickers(
    symbols: str = Query(
        default="BTC,ETH,SOL,BNB,DOGE",
        description="逗号分隔的交易对符号（不带USDT后缀）"
    ),
) -> APIResponse:
    """
    批量获取多个交易对的最新行情数据

    用于首页行情列表展示。使用 MarketService 统一调用。
    """
    # 解析交易对
    symbol_list = [s.strip().upper() + "USDT" for s in symbols.split(",") if s.strip()]

    service = MarketService(session=None)
    tickers = []

    try:
        # 使用 MarketService 的共享 httpx 客户端
        for sym in symbol_list:
            try:
                ticker = await service.get_ticker(sym, "binance")
                # P2-1: 用真实 K 线收盘价生成趋势线，替代随机数伪造
                sparkline = await _fetch_sparkline(service, sym)
                if sparkline:
                    ticker["sparkline"] = sparkline
                tickers.append(ticker)
            except Exception:
                continue

    except Exception:
        pass

    # 如果全部失败，返回模拟数据（明确标注为模拟）
    if not tickers:
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
                "price_change": change,
                "price_change_percent": change / base_price * 100,
                "volume_24h": 15000000000,
                "high_24h": base_price * 1.02,
                "low_24h": base_price * 0.98,
                "sparkline": [],
                "data_source": "mock",  # P2-1: 明确标注模拟数据
            })

    return APIResponse(data=tickers)


async def _fetch_sparkline(service: MarketService, symbol: str) -> list[float]:
    """P2-1: 获取真实 K 线收盘价作为趋势线数据"""
    try:
        klines = await service.get_kline(symbol, interval="1h", limit=8, exchange="binance")
        if klines and len(klines) >= 3:
            return [float(k.get("close", 0)) for k in klines[-8:]]
    except Exception:
        pass
    return []
