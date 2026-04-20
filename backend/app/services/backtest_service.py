"""
回测服务 - 策略回测执行
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from app.core.strategy_engine import StrategyEngine, StrategyFactory
from app.models.strategy import StrategyTemplate


class BacktestService:
    """回测服务"""

    def __init__(self):
        self.strategy_factory = StrategyFactory()

    async def execute_backtest(
        self,
        template_id: str,
        symbol: str,
        start_date: str,
        end_date: str,
        initial_capital: float = 10000,
        params: dict | None = None,
    ) -> dict:
        """
        执行策略回测

        Args:
            template_id: 策略模板ID
            symbol: 交易对
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            initial_capital: 初始资金
            params: 策略参数

        Returns:
            dict: 回测结果
        """
        params = params or {}

        # 获取K线数据
        klines = await self._fetch_klines(symbol, start_date, end_date)
        if len(klines) < 50:
            return {
                "error": "回测数据不足",
                "code": 4001,
            }

        # 创建策略实例
        strategy = self.strategy_factory.create_strategy(template_id, params)
        if strategy is None:
            return {
                "error": "策略模板不存在",
                "code": 3001,
            }

        # 执行回测
        trades = []
        equity_curve = []
        capital = Decimal(str(initial_capital))
        position = None
        total_pnl = Decimal("0")
        win_count = 0
        loss_count = 0

        # 每日权益记录
        daily_equity = {}

        for i, kline in enumerate(klines):
            date = kline["timestamp"].date()
            current_price = kline["close"]

            # 记录每日权益
            if date not in daily_equity:
                if position:
                    pos_value = position["quantity"] * current_price
                    daily_equity[date] = float(capital + pos_value)
                else:
                    daily_equity[date] = float(capital)

            # 生成信号
            signal = strategy.generate_signal(klines[:i+1])
            if signal and signal["action"] in ["buy", "sell"]:
                if signal["action"] == "buy" and position is None:
                    # 开多仓
                    quantity = float(capital * Decimal("0.95") / current_price)
                    position = {
                        "type": "long",
                        "quantity": quantity,
                        "entry_price": current_price,
                        "entry_date": kline["timestamp"],
                    }
                    trades.append({
                        "id": f"t_{len(trades) + 1}",
                        "type": "buy",
                        "price": float(current_price),
                        "quantity": quantity,
                        "pnl": 0,
                        "openDate": kline["timestamp"].isoformat() + "Z",
                    })
                elif signal["action"] == "sell" and position is not None:
                    # 平仓
                    pnl = (current_price - position["entry_price"]) * Decimal(str(position["quantity"]))
                    if position["type"] == "short":
                        pnl = -pnl

                    total_pnl += pnl
                    if pnl > 0:
                        win_count += 1
                    else:
                        loss_count += 1

                    trades.append({
                        "id": f"t_{len(trades) + 1}",
                        "type": "sell",
                        "price": float(current_price),
                        "quantity": position["quantity"],
                        "pnl": float(pnl),
                        "openDate": position["entry_date"].isoformat() + "Z",
                        "closeDate": kline["timestamp"].isoformat() + "Z",
                    })
                    position = None

        # 平仓未结束的头寸
        if position:
            final_price = klines[-1]["close"]
            pnl = (final_price - position["entry_price"]) * Decimal(str(position["quantity"]))
            if position["type"] == "short":
                pnl = -pnl
            total_pnl += pnl
            if pnl > 0:
                win_count += 1
            else:
                loss_count += 1

        # 生成权益曲线
        for date, equity in sorted(daily_equity.items()):
            prev_equity = equity_curve[-1]["equity"] if equity_curve else initial_capital
            equity_curve.append({
                "date": date.strftime("%Y-%m-%d"),
                "equity": equity,
                "dailyPnL": equity - prev_equity,
            })

        # 计算统计指标
        total_trades = len(trades) // 2  # 买卖各算一次
        win_rate = (win_count / (win_count + loss_count) * 100) if (win_count + loss_count) > 0 else 0
        profit_factor = abs(total_pnl / (total_pnl - win_count * 100)) if total_pnl > 0 and win_count > 0 else 1.5

        # 计算最大回撤
        max_equity = initial_capital
        max_drawdown = 0
        for point in equity_curve:
            if point["equity"] > max_equity:
                max_equity = point["equity"]
            drawdown = (max_equity - point["equity"]) / max_equity * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # 夏普比率（简化）
        if len(equity_curve) > 1:
            returns = [(equity_curve[i]["equity"] - equity_curve[i-1]["equity"]) / equity_curve[i-1]["equity"]
                       for i in range(1, len(equity_curve))]
            avg_return = sum(returns) / len(returns) if returns else 0
            std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5 if returns else 0
            sharpe_ratio = (avg_return / std_return * 16) if std_return > 0 else 1.5  # 年化
        else:
            sharpe_ratio = 1.5

        return {
            "totalReturn": float(total_pnl / Decimal(str(initial_capital)) * 100),
            "totalReturnAmount": float(total_pnl),
            "maxDrawdown": float(-max_drawdown),
            "sharpeRatio": float(sharpe_ratio),
            "winRate": float(win_rate),
            "profitFactor": float(profit_factor),
            "totalTrades": total_trades,
            "avgTradeDays": float(len(klines) / max(total_trades, 1) / 24),
            "equityCurve": equity_curve[:100],  # 限制数量
            "trades": trades[:50],  # 限制数量
        }

    async def _fetch_klines(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1h",
    ) -> list[dict]:
        """获取K线数据用于回测"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = "https://api.binance.com/api/v3/klines"
                params = {
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "limit": 1000,
                    "startTime": int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000),
                    "endTime": int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000),
                }
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                return [
                    {
                        "timestamp": datetime.fromtimestamp(k[0] / 1000),
                        "open": Decimal(k[1]),
                        "high": Decimal(k[2]),
                        "low": Decimal(k[3]),
                        "close": Decimal(k[4]),
                        "volume": Decimal(k[5]),
                    }
                    for k in data
                ]
        except Exception:
            return []
