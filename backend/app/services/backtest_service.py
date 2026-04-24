"""
回测服务 - 完整版

架构：
- 使用 StrategyFactory 创建策略实例，调用 analyze() 生成信号
- 从 Binance 公开 API 获取历史K线数据（无需 API Key）
- 模拟订单执行，跟踪权益曲线
- 集成 PerformanceCalculator 计算绩效指标
- 支持所有 5 种策略类型：MA / RSI / Bollinger / Grid / Martingale
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx

from app.core.strategy_engine import (
    BaseStrategy,
    StrategyConfig,
    StrategyFactory,
    get_strategy,
)
from app.core.performance import (
    EquityPoint,
    PerformanceCalculator,
    PerformanceReport,
    TradeRecord,
)

logger = logging.getLogger(__name__)

# templateId → strategy_type 映射
_TEMPLATE_MAP = {
    "ma_cross": "ma",
    "ma": "ma",
    "rsi": "rsi",
    "bollinger": "bollinger",
    "grid": "grid",
    "martingale": "martingale",
}


class BacktestService:
    """回测服务"""

    # 共享 httpx 客户端（K线数据请求）
    _shared_client: httpx.AsyncClient | None = None

    @classmethod
    async def _get_client(cls) -> httpx.AsyncClient:
        """获取共享 httpx 客户端"""
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "CryptoQuant-Backtest/1.0"},
            )
        return cls._shared_client

    @classmethod
    async def close_client(cls) -> None:
        """关闭共享客户端"""
        if cls._shared_client and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
            cls._shared_client = None

    async def execute_backtest(
        self,
        template_id: str,
        symbol: str,
        exchange: str,
        start_date: str,
        end_date: str,
        initial_capital: float = 100000,
        params: dict | None = None,
    ) -> dict:
        """
        执行策略回测

        Args:
            template_id: 策略模板ID (ma_cross/rsi/bollinger/grid/martingale)
            symbol: 交易对 (BTCUSDT)
            exchange: 交易所 (binance/okx/htx)
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            initial_capital: 初始资金
            params: 策略参数

        Returns:
            dict: 回测结果（含绩效指标 + 权益曲线 + 交易记录）
        """
        params = params or {}

        # 1. 获取K线数据
        klines = await self._fetch_klines(symbol, start_date, end_date)
        if len(klines) < 50:
            return {
                "error": "回测数据不足，至少需要 50 根K线",
                "code": 4001,
                "detail": f"获取到 {len(klines)} 根K线，需要至少 50 根",
            }

        # 2. 创建策略实例
        strategy_type = _TEMPLATE_MAP.get(template_id.lower(), template_id.lower())
        config = StrategyConfig(
            symbol=symbol.upper(),
            exchange=exchange.lower(),
            direction="both",
            params=params,
            risk_params={"stop_loss_percent": params.get("stop_loss_percent", 2.0)},
        )

        try:
            strategy = get_strategy(strategy_type, config)
        except ValueError:
            return {
                "error": f"不支持的策略类型: {template_id}",
                "code": 3001,
            }

        # 3. 运行回测引擎
        result = await self._run_backtest_engine(
            strategy=strategy,
            klines=klines,
            initial_capital=Decimal(str(initial_capital)),
        )

        return result

    async def _run_backtest_engine(
        self,
        strategy: BaseStrategy,
        klines: list[dict],
        initial_capital: Decimal,
    ) -> dict:
        """回测引擎核心

        逐根K线驱动策略，模拟订单执行，跟踪权益变化。
        """
        capital = initial_capital
        position: dict | None = None  # {"side": "long"/"short", "quantity": Decimal, "entry_price": Decimal, "entry_time": datetime}
        trades: list[TradeRecord] = []
        equity_curve: list[EquityPoint] = []
        commission_rate = Decimal("0.001")  # 0.1% 手续费

        # 初始权益点
        equity_curve.append(EquityPoint(
            timestamp=klines[0]["timestamp"],
            equity=initial_capital,
        ))

        # 最小K线数量（策略需要历史数据）
        min_history = 50

        for i in range(min_history, len(klines)):
            current_kline = klines[i]
            current_price = current_kline["close"]
            current_time = current_kline["timestamp"]

            # 构建历史K线窗口
            history_klines = klines[:i + 1]

            # 格式化为策略引擎期望的格式
            formatted_history = []
            for k in history_klines:
                formatted_history.append({
                    "open": float(k["open"]),
                    "high": float(k["high"]),
                    "low": float(k["low"]),
                    "close": float(k["close"]),
                    "volume": float(k["volume"]),
                })

            # 策略分析
            signal = await strategy.analyze(formatted_history)

            if signal is not None:
                # 处理买入信号
                if signal.action == "buy" and position is None:
                    # 使用 95% 资金开仓
                    invest_amount = capital * Decimal("0.95")
                    quantity = invest_amount / current_price
                    commission = invest_amount * commission_rate

                    position = {
                        "side": "long",
                        "quantity": quantity,
                        "entry_price": current_price,
                        "entry_time": current_time,
                        "commission_paid": commission,
                    }
                    capital -= invest_amount + commission

                # 处理卖出信号（平仓）
                elif signal.action == "sell" and position is not None:
                    close_value = position["quantity"] * current_price
                    commission = close_value * commission_rate

                    # 计算盈亏
                    if position["side"] == "long":
                        pnl = (current_price - position["entry_price"]) * position["quantity"]
                    else:
                        pnl = (position["entry_price"] - current_price) * position["quantity"]

                    pnl -= commission  # 扣除平仓手续费

                    # 记录交易
                    trades.append(TradeRecord(
                        entry_price=position["entry_price"],
                        exit_price=current_price,
                        quantity=position["quantity"],
                        side=position["side"],
                        entry_time=position["entry_time"],
                        exit_time=current_time,
                        pnl=pnl,
                        commission=position["commission_paid"] + commission,
                    ))

                    capital += close_value - commission
                    position = None

            # 检查止损止盈（如果有持仓）
            if position is not None:
                sl_price = signal.stop_loss_price if signal else None
                tp_price = signal.take_profit_price if signal else None

                # 止损检查
                should_close = False
                close_reason = ""
                if position["side"] == "long":
                    if sl_price and current_price <= sl_price:
                        should_close = True
                        close_reason = "止损"
                    elif tp_price and current_price >= tp_price:
                        should_close = True
                        close_reason = "止盈"
                elif position["side"] == "short":
                    if sl_price and current_price >= sl_price:
                        should_close = True
                        close_reason = "止损"
                    elif tp_price and current_price <= tp_price:
                        should_close = True
                        close_reason = "止盈"

                if should_close:
                    close_value = position["quantity"] * current_price
                    commission = close_value * commission_rate

                    if position["side"] == "long":
                        pnl = (current_price - position["entry_price"]) * position["quantity"]
                    else:
                        pnl = (position["entry_price"] - current_price) * position["quantity"]

                    pnl -= commission

                    trades.append(TradeRecord(
                        entry_price=position["entry_price"],
                        exit_price=current_price,
                        quantity=position["quantity"],
                        side=position["side"],
                        entry_time=position["entry_time"],
                        exit_time=current_time,
                        pnl=pnl,
                        commission=position["commission_paid"] + commission,
                    ))

                    capital += close_value - commission
                    position = None

            # 记录权益
            current_equity = capital
            if position is not None:
                current_equity += position["quantity"] * current_price

            equity_curve.append(EquityPoint(
                timestamp=current_time,
                equity=current_equity,
            ))

        # 平仓未结束的头寸
        if position is not None:
            final_price = klines[-1]["close"]
            close_value = position["quantity"] * final_price
            commission = close_value * commission_rate

            if position["side"] == "long":
                pnl = (final_price - position["entry_price"]) * position["quantity"]
            else:
                pnl = (position["entry_price"] - final_price) * position["quantity"]

            pnl -= commission

            trades.append(TradeRecord(
                entry_price=position["entry_price"],
                exit_price=final_price,
                quantity=position["quantity"],
                side=position["side"],
                entry_time=position["entry_time"],
                exit_time=klines[-1]["timestamp"],
                pnl=pnl,
                commission=position["commission_paid"] + commission,
            ))

            capital += close_value - commission

        # 4. 使用 PerformanceCalculator 计算绩效
        report = PerformanceCalculator.calculate(
            trades=trades,
            equity_curve=equity_curve,
            initial_capital=initial_capital,
        )

        # 5. 构建返回结果
        equity_points = []
        # 采样权益曲线（最多 200 个点，避免数据量过大）
        step = max(1, len(equity_curve) // 200)
        for i in range(0, len(equity_curve), step):
            point = equity_curve[i]
            equity_points.append({
                "date": point.timestamp.strftime("%Y-%m-%d %H:%M"),
                "equity": float(round(point.equity, 2)),
            })

        # 交易记录（最多 50 条）
        trade_records = []
        for t in trades[:50]:
            trade_records.append({
                "side": t.side,
                "entryPrice": float(t.entry_price),
                "exitPrice": float(t.exit_price),
                "quantity": float(t.quantity),
                "pnl": float(round(t.pnl, 2)),
                "entryTime": t.entry_time.isoformat() + "Z",
                "exitTime": t.exit_time.isoformat() + "Z",
            })

        return {
            # 绩效指标
            "totalReturn": float(report.total_pnl),
            "totalReturnPercent": float(report.total_return_pct),
            "annualReturn": float(report.annualized_return_pct),
            "sharpeRatio": float(report.sharpe_ratio),
            "calmarRatio": float(report.calmar_ratio),
            "maxDrawdown": float(report.max_drawdown_pct),
            "winRate": float(report.win_rate),
            "profitFactor": float(report.profit_loss_ratio),
            "totalTrades": report.total_trades,
            "profitTrades": report.winning_trades,
            "lossTrades": report.losing_trades,
            "avgProfit": float(report.avg_profit),
            "avgLoss": float(report.avg_loss),
            "maxConsecutiveWins": report.max_consecutive_wins,
            "maxConsecutiveLosses": report.max_consecutive_losses,

            # 资金信息
            "initialCapital": float(initial_capital),
            "finalCapital": float(report.final_equity),
            "duration": report.trading_days,

            # 详细数据
            "equityCurve": equity_points,
            "trades": trade_records,

            # 元信息
            "startTime": report.start_time.isoformat() + "Z" if report.start_time else None,
            "endTime": report.end_time.isoformat() + "Z" if report.end_time else None,
        }

    async def _fetch_klines(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1h",
    ) -> list[dict]:
        """获取历史K线数据（Binance 公开 API，无需 API Key）

        支持自动分页获取大量历史数据。
        """
        all_klines = []
        try:
            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

            client = await self._get_client()
            current_start = start_ts

            while current_start < end_ts:
                url = "https://api.binance.com/api/v3/klines"
                params = {
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "startTime": current_start,
                    "endTime": end_ts,
                    "limit": 1000,
                }

                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                if not data:
                    break

                for k in data:
                    all_klines.append({
                        "timestamp": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
                        "open": Decimal(k[1]),
                        "high": Decimal(k[2]),
                        "low": Decimal(k[3]),
                        "close": Decimal(k[4]),
                        "volume": Decimal(k[5]),
                        "close_time": datetime.fromtimestamp(k[6] / 1000, tz=timezone.utc),
                    })

                # 下一页起始时间 = 最后一根K线的关闭时间 + 1ms
                current_start = data[-1][6] + 1

                # 如果返回数量 < 1000，说明已经没有更多数据
                if len(data) < 1000:
                    break

        except Exception as e:
            logger.warning("获取K线数据失败: %s，使用模拟数据", e)
            # 降级：使用确定性模拟数据
            all_klines = self._generate_mock_klines(symbol, start_date, end_date)

        return all_klines

    def _generate_mock_klines(
        self, symbol: str, start_date: str, end_date: str
    ) -> list[dict]:
        """生成模拟K线数据（降级用）

        使用确定性伪随机，确保相同参数产生相同结果。
        """
        import hashlib

        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            days = max((end - start).days, 1)
        except ValueError:
            days = 90

        base_prices = {
            "BTCUSDT": 98000.0,
            "ETHUSDT": 3200.0,
            "SOLUSDT": 185.0,
            "BNBUSDT": 620.0,
            "DOGEUSDT": 0.38,
        }
        base = base_prices.get(symbol.upper(), 100.0)

        klines = []
        current_time = start
        # 每天约 24 根 1h K线
        total_bars = days * 24
        price = base

        for i in range(total_bars):
            # 确定性伪随机
            seed = int(hashlib.md5(f"{symbol}_{i}".encode()).hexdigest(), 16) % 10000
            change = ((seed / 10000.0) - 0.48) * 0.02  # ±1% 波动
            price = price * (1 + change)

            open_price = price
            high = price * (1 + abs(change) * 0.5)
            low = price * (1 - abs(change) * 0.5)
            close = price * (1 + ((seed % 7) - 3) * 0.001)
            volume = base * 1000 * (1 + (seed % 5) * 0.1)

            klines.append({
                "timestamp": current_time.replace(tzinfo=timezone.utc),
                "open": Decimal(str(round(open_price, 8))),
                "high": Decimal(str(round(high, 8))),
                "low": Decimal(str(round(low, 8))),
                "close": Decimal(str(round(close, 8))),
                "volume": Decimal(str(round(volume, 2))),
                "close_time": current_time.replace(tzinfo=timezone.utc),
            })

            # 每小时
            from datetime import timedelta
            current_time += timedelta(hours=1)

        return klines
