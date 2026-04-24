"""
回测服务 v2 - 内存优化版

核心优化：
1. K线数据量上限 5000 根，跨度过大自动升级时间级别（1h→4h→1d）
2. 策略分析只传滑动窗口（最近 200 根），不再全量拷贝
3. 权益曲线实时采样，不累积全量 EquityPoint 对象
4. 超时保护：最长 60 秒
5. K线预转换为 float，避免循环内重复转换
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
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

# 时间级别配置：(interval, 每天约多少根, 最大支持天数)
_INTERVAL_CONFIG = [
    ("1h", 24, 200),    # 200天以内用1h
    ("4h", 6, 800),     # 200-800天用4h
    ("1d", 1, 3650),    # 800天-10年用1d
]

# 策略分析用滑动窗口大小
_ANALYSIS_WINDOW = 200

# 最大K线数量
_MAX_KLINES = 5000

# 回测超时（秒）
_BACKTEST_TIMEOUT = 60


class BacktestService:
    """回测服务 v2"""

    _shared_client: httpx.AsyncClient | None = None

    @classmethod
    async def _get_client(cls) -> httpx.AsyncClient:
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "CryptoQuant-Backtest/1.0"},
            )
        return cls._shared_client

    @classmethod
    async def close_client(cls) -> None:
        if cls._shared_client and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
            cls._shared_client = None

    def _select_interval(self, start_date: str, end_date: str) -> tuple[str, str]:
        """根据日期跨度自动选择K线时间级别"""
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            days = (end - start).days
        except ValueError:
            days = 90

        for interval, bars_per_day, max_days in _INTERVAL_CONFIG:
            if days <= max_days:
                label_map = {"1h": "1小时", "4h": "4小时", "1d": "日线"}
                return interval, label_map.get(interval, interval)

        return "1d", "日线"

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
        """执行策略回测"""
        params = params or {}
        start_time = time.monotonic()

        # 自动选择时间级别
        interval, interval_label = self._select_interval(start_date, end_date)

        # 1. 获取K线数据
        klines = await self._fetch_klines(symbol, start_date, end_date, interval=interval)
        if len(klines) < 50:
            return {
                "error": "回测数据不足，至少需要 50 根K线",
                "code": 4001,
                "detail": f"获取到 {len(klines)} 根K线（{interval_label}级别），需要至少 50 根",
            }

        # 截取
        if len(klines) > _MAX_KLINES:
            klines = klines[-_MAX_KLINES:]

        data_source = "mock" if getattr(self, "_using_mock_data", True) else "binance"

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
            return {"error": f"不支持的策略类型: {template_id}", "code": 3001}

        # 3. 运行回测引擎（带超时保护）
        try:
            result = await asyncio.wait_for(
                self._run_backtest_engine(
                    strategy=strategy,
                    klines=klines,
                    initial_capital=Decimal(str(initial_capital)),
                    interval_label=interval_label,
                    data_source=data_source,
                ),
                timeout=_BACKTEST_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return {
                "error": f"回测超时（{_BACKTEST_TIMEOUT}秒），请缩小时间范围",
                "code": 4002,
            }

        elapsed = time.monotonic() - start_time
        result["elapsedSeconds"] = round(elapsed, 1)
        result["interval"] = interval_label
        result["klineCount"] = len(klines)

        return result

    async def _run_backtest_engine(
        self,
        strategy: BaseStrategy,
        klines: list[dict],
        initial_capital: Decimal,
        interval_label: str = "",
        data_source: str = "mock",
    ) -> dict:
        """回测引擎核心 v2 — 内存优化版

        关键优化：
        1. 策略分析只传滑动窗口 float_klines[window_start:i+1]
        2. 预转换 float 格式，不循环内创建新 list
        3. 权益曲线在采样点直接写入 dict，不累积 EquityPoint
        4. 同时维护精确 EquityPoint 列表供绩效计算（采样间隔保存）
        """
        capital = initial_capital
        position: dict | None = None
        trades: list[TradeRecord] = []
        commission_rate = Decimal("0.001")

        # 预转换K线为 float 格式（只做一次，O(n)）
        float_klines = [
            {
                "open": float(k["open"]),
                "high": float(k["high"]),
                "low": float(k["low"]),
                "close": float(k["close"]),
                "volume": float(k["volume"]),
            }
            for k in klines
        ]

        min_history = 50

        # 权益曲线采样：用于前端展示（最多 200 个点）
        _sample_step = max(1, (len(klines) - min_history) // 200)
        display_equity: list[dict] = []

        # 精确权益曲线：用于绩效计算（采样保存，最多 500 个点）
        _perf_step = max(1, (len(klines) - min_history) // 500)
        perf_equity: list[EquityPoint] = [
            EquityPoint(timestamp=klines[0]["timestamp"], equity=initial_capital)
        ]

        # 初始展示点
        display_equity.append({
            "date": klines[0]["timestamp"].strftime("%Y-%m-%d %H:%M"),
            "equity": float(initial_capital),
        })

        for i in range(min_history, len(klines)):
            current_price = klines[i]["close"]
            current_time = klines[i]["timestamp"]

            # 滑动窗口：只传最近 _ANALYSIS_WINDOW 根给策略
            window_start = max(0, i - _ANALYSIS_WINDOW + 1)
            history_slice = float_klines[window_start:i + 1]

            # 策略分析
            signal = await strategy.analyze(history_slice)

            # 交易逻辑
            if signal is not None:
                if signal.action == "buy" and position is None:
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

                elif signal.action == "sell" and position is not None:
                    close_value = position["quantity"] * current_price
                    commission = close_value * commission_rate

                    pnl = (current_price - position["entry_price"]) * position["quantity"] \
                        if position["side"] == "long" \
                        else (position["entry_price"] - current_price) * position["quantity"]
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

            # 止损止盈
            if position is not None:
                sl_price = signal.stop_loss_price if signal else None
                tp_price = signal.take_profit_price if signal else None

                should_close = False
                if position["side"] == "long":
                    if (sl_price and current_price <= sl_price) or (tp_price and current_price >= tp_price):
                        should_close = True
                else:
                    if (sl_price and current_price >= sl_price) or (tp_price and current_price <= tp_price):
                        should_close = True

                if should_close:
                    close_value = position["quantity"] * current_price
                    commission = close_value * commission_rate

                    pnl = (current_price - position["entry_price"]) * position["quantity"] \
                        if position["side"] == "long" \
                        else (position["entry_price"] - current_price) * position["quantity"]
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

            # 当前权益
            current_equity = capital
            if position is not None:
                current_equity += position["quantity"] * current_price

            # 采样：展示权益曲线
            idx = i - min_history
            if idx % _sample_step == 0:
                display_equity.append({
                    "date": current_time.strftime("%Y-%m-%d %H:%M"),
                    "equity": float(round(current_equity, 2)),
                })

            # 采样：绩效权益曲线
            if idx % _perf_step == 0:
                perf_equity.append(EquityPoint(
                    timestamp=current_time,
                    equity=current_equity,
                ))

        # 平仓未结束的头寸
        if position is not None:
            final_price = klines[-1]["close"]
            close_value = position["quantity"] * final_price
            commission = close_value * commission_rate

            pnl = (final_price - position["entry_price"]) * position["quantity"] \
                if position["side"] == "long" \
                else (position["entry_price"] - final_price) * position["quantity"]
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
            position = None

        # 最终权益
        final_equity = capital
        display_equity.append({
            "date": klines[-1]["timestamp"].strftime("%Y-%m-%d %H:%M"),
            "equity": float(round(final_equity, 2)),
        })
        perf_equity.append(EquityPoint(
            timestamp=klines[-1]["timestamp"],
            equity=final_equity,
        ))

        # 绩效计算
        report = PerformanceCalculator.calculate(
            trades=trades,
            equity_curve=perf_equity,
            initial_capital=initial_capital,
        )

        # 交易记录（最多 100 条）
        trade_records = []
        for t in trades[:100]:
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
            "initialCapital": float(initial_capital),
            "finalCapital": float(report.final_equity),
            "duration": report.trading_days,
            "equityCurve": display_equity,
            "trades": trade_records,
            "startTime": report.start_time.isoformat() + "Z" if report.start_time else None,
            "endTime": report.end_time.isoformat() + "Z" if report.end_time else None,
            "dataSource": data_source,
            "warning": "⚠️ 使用模拟数据回测，结果可能失真，仅供参考" if data_source == "mock" else None,
        }

    async def _fetch_klines(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1h",
    ) -> list[dict]:
        """获取历史K线数据（Binance 公开 API）

        内置最大数量限制 _MAX_KLINES，超过自动截断。
        """
        all_klines = []
        try:
            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

            client = await self._get_client()
            current_start = start_ts

            while current_start < end_ts and len(all_klines) < _MAX_KLINES:
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

                current_start = data[-1][6] + 1

                if len(data) < 1000:
                    break

                if len(all_klines) >= _MAX_KLINES:
                    logger.warning(
                        "K线数量已达上限 %d，截断。interval=%s, %s ~ %s",
                        _MAX_KLINES, interval, start_date, end_date,
                    )
                    break

        except Exception as e:
            logger.warning("获取K线数据失败: %s，使用模拟数据", e)
            all_klines = self._generate_mock_klines(symbol, start_date, end_date, interval)
            self._using_mock_data = True
        else:
            self._using_mock_data = False

        return all_klines

    def _generate_mock_klines(
        self, symbol: str, start_date: str, end_date: str, interval: str = "1h"
    ) -> list[dict]:
        """生成模拟K线数据（降级用）

        根据 interval 自动调整生成频率，总量不超过 _MAX_KLINES。
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

        interval_hours = {"1m": 1/60, "5m": 5/60, "15m": 15/60, "30m": 30/60, "1h": 1, "4h": 4, "1d": 24}
        hours_per_bar = interval_hours.get(interval, 1)
        total_bars = min(int(days * 24 / hours_per_bar), _MAX_KLINES)

        klines = []
        current_time = start.replace(tzinfo=timezone.utc)
        price = base

        for i in range(total_bars):
            seed = int(hashlib.md5(f"{symbol}_{interval}_{i}".encode()).hexdigest(), 16) % 10000
            change = ((seed / 10000.0) - 0.48) * 0.02
            price = price * (1 + change)

            open_price = price
            high = price * (1 + abs(change) * 0.5)
            low = price * (1 - abs(change) * 0.5)
            close = price * (1 + ((seed % 7) - 3) * 0.001)
            volume = base * 1000 * (1 + (seed % 5) * 0.1)

            klines.append({
                "timestamp": current_time,
                "open": Decimal(str(round(open_price, 8))),
                "high": Decimal(str(round(high, 8))),
                "low": Decimal(str(round(low, 8))),
                "close": Decimal(str(round(close, 8))),
                "volume": Decimal(str(round(volume, 2))),
                "close_time": current_time,
            })

            current_time += timedelta(hours=hours_per_bar)

        return klines
