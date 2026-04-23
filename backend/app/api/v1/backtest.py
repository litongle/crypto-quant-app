"""
回测 API
"""
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.schemas import APIResponse
from app.models.user import User

router = APIRouter()


# ============ 请求模型 ============

class BacktestRequest(BaseModel):
    """回测请求"""
    templateId: str = Field(..., description="策略模板ID (ma_cross/rsi/bollinger/grid)")
    symbol: str = Field(..., description="交易对 (BTCUSDT)")
    exchange: str = Field(default="binance", description="交易所")
    startDate: str = Field(..., description="开始日期 YYYY-MM-DD")
    endDate: str = Field(default="", description="结束日期 YYYY-MM-DD，默认今天")
    initialCapital: float = Field(default=10000.0, gt=0, description="初始资金 USDT，必须大于0")
    params: dict = Field(default_factory=dict, description="策略参数")


class BacktestResult(BaseModel):
    """回测结果"""
    totalReturn: float = Field(..., description="总收益率 (%)")
    totalReturnPercent: float = Field(..., description="总收益率百分比")
    sharpeRatio: float = Field(..., description="夏普比率")
    maxDrawdown: float = Field(..., description="最大回撤 (%)")
    maxDrawdownPercent: float = Field(..., description="最大回撤百分比")
    winRate: float = Field(..., description="胜率 (%)")
    totalTrades: int = Field(..., description="总交易次数")
    profitTrades: int = Field(..., description="盈利次数")
    lossTrades: int = Field(..., description="亏损次数")
    avgProfit: float = Field(..., description="平均盈利")
    avgLoss: float = Field(..., description="平均亏损")
    profitFactor: float = Field(..., description="盈亏比")
    annualReturn: float = Field(..., description="年化收益率 (%)")
    volatility: float = Field(..., description="波动率 (%)")
    finalCapital: float = Field(..., description="最终资金")
    duration: int = Field(..., description="回测天数")
    equityCurve: list[dict] = Field(..., description="权益曲线数据点")


# ============ 简化回测引擎 ============

def _run_ma_cross(params: dict, prices: list[float], capital: float) -> BacktestResult:
    """双均线策略回测"""
    fast = int(params.get('fastPeriod', 5))
    slow = int(params.get('slowPeriod', 20))

    cash = capital
    position = 0.0
    trades = []
    equity = [capital]
    wins, losses = 0, 0
    total_profit, total_loss = 0.0, 0.0

    for i in range(slow, len(prices)):
        ma_fast = sum(prices[i - fast:i]) / fast
        ma_slow = sum(prices[i - slow:i]) / slow
        prev_fast = sum(prices[i - fast - 1:i - 1]) / fast
        prev_slow = sum(prices[i - slow - 1:i - slow]) / slow

        price = prices[i]

        # 金叉买入
        if prev_fast <= prev_slow and ma_fast > ma_slow and position == 0 and cash > 0:
            position = cash / price
            cash = 0
            trades.append({'type': 'buy', 'price': price, 'i': i})

        # 死叉卖出
        elif prev_fast >= prev_slow and ma_fast < ma_slow and position > 0:
            cash = position * price
            pnl = cash - capital if len(trades) == 1 else 0
            if pnl > 0:
                wins += 1
                total_profit += pnl
            else:
                losses += 1
                total_loss += abs(pnl)
            position = 0
            trades.append({'type': 'sell', 'price': price, 'i': i})

        equity.append(cash + position * price if position > 0 else cash)

    final_capital = cash + position * prices[-1] if position > 0 else cash
    total_return = final_capital - capital
    total_return_pct = (total_return / capital) * 100

    # 权益曲线简化
    days = len(prices)
    equity_points = [
        {'date': (datetime.now() - timedelta(days=days - i)).strftime('%Y-%m-%d'),
         'equity': round(e, 2)}
        for i, e in enumerate(equity)
    ]

    max_dd = 0.0
    peak = capital
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100
        if dd > max_dd:
            max_dd = dd

    wins_count = max(wins, 0)
    losses_count = max(losses, 0)
    win_rate = wins_count / (wins_count + losses_count) * 100 if (wins_count + losses_count) > 0 else 0

    return BacktestResult(
        totalReturn=round(total_return, 2),
        totalReturnPercent=round(total_return_pct, 2),
        sharpeRatio=round(_calculate_sharpe_ratio(equity), 2),
        maxDrawdown=round(max_dd * capital / 100, 2),
        maxDrawdownPercent=round(max_dd, 2),
        winRate=round(win_rate, 1),
        totalTrades=len(trades),
        profitTrades=wins_count,
        lossTrades=losses_count,
        avgProfit=round(total_profit / wins_count, 2) if wins_count > 0 else 0,
        avgLoss=round(total_loss / losses_count, 2) if losses_count > 0 else 0,
        profitFactor=round(total_profit / total_loss, 2) if total_loss > 0 else 0,
        annualReturn=round(total_return_pct / (days / 365) if days > 0 else 0, 2),
        volatility=round(_calculate_volatility(prices), 1),
        finalCapital=round(final_capital, 2),
        duration=days,
        equityCurve=equity_points,
    )


def _run_rsi(params: dict, prices: list[float], capital: float) -> BacktestResult:
    """RSI策略回测（简化版）"""
    period = int(params.get('period', 14))
    oversold = int(params.get('oversold', 30))
    overbought = int(params.get('overbought', 70))

    cash = capital
    position = 0.0
    trades = []
    equity = [capital]
    wins, losses = 0, 0
    total_profit, total_loss = 0.0, 0.0

    for i in range(period, len(prices)):
        gains, losses_list = 0.0, 0.0
        for j in range(i - period, i):
            diff = prices[j + 1] - prices[j]
            if diff > 0:
                gains += diff
            else:
                losses_list += abs(diff)

        avg_gain = gains / period
        avg_loss = losses_list / period
        rsi = (avg_gain / (avg_gain + avg_loss) * 100) if (avg_gain + avg_loss) > 0 else 50

        price = prices[i]

        if rsi < oversold and position == 0 and cash > 0:
            position = cash / price
            cash = 0
            trades.append({'type': 'buy', 'price': price})

        elif rsi > overbought and position > 0:
            cash = position * price
            position = 0
            trades.append({'type': 'sell', 'price': price})

        equity.append(cash + position * price if position > 0 else cash)

    final_capital = cash + position * prices[-1] if position > 0 else cash
    total_return = final_capital - capital
    total_return_pct = (total_return / capital) * 100

    days = len(prices)
    equity_points = [
        {'date': (datetime.now() - timedelta(days=days - i)).strftime('%Y-%m-%d'),
         'equity': round(e, 2)}
        for i, e in enumerate(equity)
    ]

    max_dd = 0.0
    peak = capital
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100
        if dd > max_dd:
            max_dd = dd

    wins_count = max(wins, 0)
    losses_count = max(losses, 0)
    win_rate = wins_count / (wins_count + losses_count) * 100 if (wins_count + losses_count) > 0 else 0

    return BacktestResult(
        totalReturn=round(total_return, 2),
        totalReturnPercent=round(total_return_pct, 2),
        sharpeRatio=round(_calculate_sharpe_ratio(equity), 2),
        maxDrawdown=round(max_dd * capital / 100, 2),
        maxDrawdownPercent=round(max_dd, 2),
        winRate=round(win_rate, 1),
        totalTrades=len(trades),
        profitTrades=wins_count,
        lossTrades=losses_count,
        avgProfit=round(total_profit / wins_count, 2) if wins_count > 0 else 0,
        avgLoss=round(total_loss / losses_count, 2) if losses_count > 0 else 0,
        profitFactor=round(total_profit / total_loss, 2) if total_loss > 0 else 0,
        annualReturn=round(total_return_pct / (days / 365) if days > 0 else 0, 2),
        volatility=round(_calculate_volatility(prices), 1),
        finalCapital=round(final_capital, 2),
        duration=days,
        equityCurve=equity_points,
    )


def _generate_mock_prices(symbol: str, days: int) -> list[float]:
    """生成模拟价格数据（用于演示，生产环境应从行情服务获取）

    注意：模拟数据仅供演示，回测指标基于模拟价格计算，非真实市场数据。
    生产环境应替换为真实K线数据。
    """
    import hashlib
    base_prices = {
        'BTCUSDT': 98000.0,
        'ETHUSDT': 3200.0,
        'SOLUSDT': 185.0,
        'BNBUSDT': 620.0,
        'DOGEUSDT': 0.38,
    }
    base = base_prices.get(symbol.upper(), 100.0)
    prices = [base]

    # 使用确定性伪随机（基于symbol哈希），而非 random 模块
    for i in range(days):
        seed = int(hashlib.md5(f"{symbol}_{i}".encode()).hexdigest(), 16) % 10000
        change = ((seed / 10000.0) - 0.48) * 0.04
        prices.append(prices[-1] * (1 + change))

    return prices


def _calculate_sharpe_ratio(equity: list[float]) -> float:
    """基于权益曲线计算夏普比率（年化）"""
    if len(equity) < 2:
        return 0.0
    returns = [(equity[i] - equity[i-1]) / equity[i-1] for i in range(1, len(equity))]
    if not returns:
        return 0.0
    avg_return = sum(returns) / len(returns)
    variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
    std_return = variance ** 0.5
    if std_return == 0:
        return 0.0
    # 年化：假设日频数据，252个交易日
    return (avg_return / std_return) * (252 ** 0.5)


def _calculate_volatility(prices: list[float]) -> float:
    """基于价格序列计算年化波动率"""
    if len(prices) < 2:
        return 0.0
    returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
    if not returns:
        return 0.0
    avg_return = sum(returns) / len(returns)
    variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
    daily_vol = variance ** 0.5
    # 年化波动率
    return daily_vol * (252 ** 0.5) * 100


# ============ 路由 ============

@router.post("/run")
async def run_backtest(
    request: BacktestRequest,
    current_user: CurrentUser,
) -> APIResponse:
    """
    运行回测

    基于给定的策略参数和时间范围，运行历史数据回测并返回绩效指标。
    """
    # 解析日期
    try:
        start = datetime.strptime(request.startDate, '%Y-%m-%d')
        end = datetime.strptime(request.endDate, '%Y-%m-%d') if request.endDate else datetime.now()
        days = max((end - start).days, 1)
    except ValueError:
        days = 365

    # 获取模拟价格数据（生产环境应调用 MarketService 获取真实 K 线）
    prices = _generate_mock_prices(request.symbol, min(days, 365))

    # 根据策略模板运行回测
    template_id = request.templateId.lower()
    if template_id in ('ma_cross', 'ma', 'ma_cross_strategy'):
        result = _run_ma_cross(request.params, prices, request.initialCapital)
    elif template_id in ('rsi', 'rsi_strategy'):
        result = _run_rsi(request.params, prices, request.initialCapital)
    elif template_id in ('bollinger', 'bollinger_strategy'):
        # 布林带策略 - 使用均线策略近似
        result = _run_ma_cross(request.params, prices, request.initialCapital)
    elif template_id in ('grid', 'grid_strategy'):
        # 网格策略 - 简化模拟
        result = _run_ma_cross({'fastPeriod': 10, 'slowPeriod': 50}, prices, request.initialCapital)
    elif template_id in ('martingale',):
        result = _run_rsi({'period': 14, 'oversold': 30, 'overbought': 70}, prices, request.initialCapital)
    else:
        # 默认使用均线策略
        result = _run_ma_cross({'fastPeriod': 5, 'slowPeriod': 20}, prices, request.initialCapital)

    return APIResponse(data=result.model_dump())


@router.get("/history")
async def get_backtest_history(
    current_user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
) -> APIResponse:
    """
    获取回测历史记录

    返回用户最近的回测历史。
    """
    # TODO: 从数据库加载历史记录
    return APIResponse(data=[])


@router.get("/{backtest_id}")
async def get_backtest_result(
    backtest_id: int,
    current_user: CurrentUser,
) -> APIResponse:
    """
    获取回测结果详情
    """
    # TODO: 从数据库加载回测结果
    return APIResponse(code=3001, message="回测记录不存在")
