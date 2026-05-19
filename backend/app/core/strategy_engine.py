"""
策略引擎基类及具体策略实现
"""

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from decimal import Decimal
from math import floor
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel

from app.core.indicators import calc_bollinger

logger = logging.getLogger(__name__)


class StrategyConfig(BaseModel):
    """策略配置"""

    symbol: str
    exchange: str
    direction: Literal["long", "short", "both"] = "both"
    params: dict[str, Any] = {}
    risk_params: dict[str, Any] = {}
    #: 与前端 *.P / params.market_type 对齐，供 Runner 选永续 K 线与下单路由
    is_perp: bool = False


class Signal(BaseModel):
    """策略生成的信号

    metadata 由具体策略填充结构化语义（intent/direction 等），
    runner 可据此判断这是开仓 / 加仓 / 平仓 / 反手。Step 2 起会被消费。
    """

    action: Literal["buy", "sell", "hold"]
    confidence: float = 1.0
    entry_price: Decimal | None = None
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    reason: str | None = None
    timestamp: datetime = datetime.now(UTC)
    metadata: dict[str, Any] = {}


class BaseStrategy(ABC):
    """策略基类"""

    name: str = "Base Strategy"
    strategy_type: str = "base"

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.params = config.params
        self.risk_params = config.risk_params

    @abstractmethod
    async def analyze(self, klines: list[dict]) -> Signal | None:
        """分析K线并生成信号"""
        pass

    # Step 3: 状态序列化 — 默认空,有状态策略(如 RsiLayered)需重写
    #
    # 默认无状态: MA / RSI(简化版) / Rule 三个内置策略不持有 tick 间状态,
    # 重启可从零开始算。RsiLayered 这类复杂状态机必须 override 这两个方法。

    def to_dict(self) -> dict[str, Any]:
        """导出策略状态(用于持久化)。无状态策略返回空 dict。"""
        return {}

    def from_dict(self, data: dict[str, Any]) -> None:
        """从字典恢复策略状态。无状态策略空操作。"""
        return None


class MAStrategy(BaseStrategy):
    """移动平均线策略"""

    name = "均线交叉策略"
    strategy_type = "ma"

    async def analyze(self, klines: list[dict]) -> Signal | None:
        # 参数:短周期和长周期均线窗口,默认 5 和 20。
        # seed_data 模板用 fastPeriod/slowPeriod (camelCase) 暴露给前端,
        # 早期代码用 short_window/long_window 字段读 — 两套不一致让所有 MA
        # 回测永远跑默认 (5,20), 用户改参数无效。fallback 同时识别两个命名,
        # 优先 seed_data 命名以匹配前端 UI。
        short_window = int(self.params.get("fastPeriod") or self.params.get("short_window") or 5)
        long_window = int(self.params.get("slowPeriod") or self.params.get("long_window") or 20)

        if len(klines) < long_window + 1:  # 需要 prev 这一根
            return None

        # 性能 — 之前 closes 用 Decimal(str(...)) 转全 N 根, 回测主循环 O(N²) 在 5万根
        # 上 35000 次 analyze × 35000 次 Decimal 转 = 12 亿次,实测从 273 bar/s 降到
        # 183 bar/s。MA 是趋势判断不需要 Decimal 精度,float 求和 + 除法 + 比较够用,
        # 且只需要末尾 long_window+1 根来算两点 MA。这两步合一砍掉 99% 计算量。
        slice_for_ma = klines[-(long_window + 1) :]
        closes = [float(k["close"]) for k in slice_for_ma]

        def calc_ma(data: list[float], window: int) -> float | None:
            if len(data) < window:
                return None
            return sum(data[-window:]) / window

        short_ma = calc_ma(closes, short_window)
        long_ma = calc_ma(closes, long_window)
        if short_ma is None or long_ma is None:
            return None

        prev_short_ma = calc_ma(closes[:-1], short_window)
        prev_long_ma = calc_ma(closes[:-1], long_window)
        if prev_short_ma is None or prev_long_ma is None:
            return None

        if prev_short_ma <= prev_long_ma and short_ma > long_ma:
            return Signal(
                action="buy",
                confidence=0.8,
                entry_price=Decimal(str(closes[-1])),
                reason=f"MA Golden Cross (MA{short_window} crossed above MA{long_window})",
                metadata={"short_ma": short_ma, "long_ma": long_ma},
            )

        if prev_short_ma >= prev_long_ma and short_ma < long_ma:
            return Signal(
                action="sell",
                confidence=0.8,
                entry_price=Decimal(str(closes[-1])),
                reason=f"MA Death Cross (MA{short_window} crossed below MA{long_window})",
                metadata={"short_ma": short_ma, "long_ma": long_ma},
            )

        return None


class RSIStrategy(BaseStrategy):
    """RSI 策略"""

    name = "RSI 超买超卖策略"
    strategy_type = "rsi"

    async def analyze(self, klines: list[dict]) -> Signal | None:
        # 标准 RSI 周期为 14
        period = self.params.get("period", 14)
        oversold = self.params.get("oversold", 30)
        overbought = self.params.get("overbought", 70)

        if len(klines) < period + 1:
            return None

        # 性能 — 之前每次 analyze build 全 N 根 closes + smoothing loop O(N),
        # 主循环 O(N²)。Wilder RSI 是 EMA 平滑, 6 个半衰期(period * 6)后远古数据
        # 权重 < 0.01% 可忽略。取 period * 6 切片够精度,把 O(N²)→O(period²)。
        window = period * 6
        closes = [float(k["close"]) for k in klines[-window:]]

        # 计算变动值
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

        # 分离涨跌
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        # 初始平均
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # 平滑计算
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        current_price = closes[-1]

        # 超卖买入信号
        if rsi < oversold:
            return Signal(
                action="buy",
                confidence=min(0.9, (oversold - rsi) / oversold + 0.5),
                entry_price=Decimal(str(current_price)),
                reason=f"RSI oversold ({rsi:.1f} < {oversold})",
                metadata={"rsi": round(rsi, 2), "period": period},
            )

        # 超买卖出信号
        if rsi > overbought:
            return Signal(
                action="sell",
                confidence=min(0.9, (rsi - overbought) / (100 - overbought) + 0.5),
                entry_price=Decimal(str(current_price)),
                reason=f"RSI overbought ({rsi:.1f} > {overbought})",
                metadata={"rsi": round(rsi, 2), "period": period},
            )

        return None


class BollingerStrategy(BaseStrategy):
    """布林带均值回归策略"""

    name = "布林带策略"
    strategy_type = "bollinger"

    async def analyze(self, klines: list[dict]) -> Signal | None:
        period = int(self.params.get("period", 20))
        std_dev = float(self.params.get("stdDev", 2.0))

        if len(klines) < period + 1:
            return None

        # 性能 — Bollinger 是 SMA + 标准差, 算 close_now/close_prev 两点上下轨
        # 只需要末尾 period+1 根 (period 算当前+SMA, prev 用前 period 根)。
        # 之前每次 build 全 N 根 closes + calc_bollinger 整个数组,O(N²) 在 5万根
        # K 线上巨慢。取 period+1 切片精度无损。
        slice_for_bb = klines[-(period + 1) :]
        closes = [float(k["close"]) for k in slice_for_bb]
        close_now = closes[-1]
        close_prev = closes[-2]
        upper, middle, lower, pct_b = calc_bollinger(np.array(closes), period, std_dev)
        upper_now = float(upper[-1])
        lower_now = float(lower[-1])
        upper_prev = float(upper[-2])
        lower_prev = float(lower[-2])

        if close_prev > lower_prev and close_now <= lower_now:
            return Signal(
                action="buy",
                confidence=0.78,
                entry_price=Decimal(str(close_now)),
                reason=f"Bollinger lower band touch ({close_now:.2f} <= {lower_now:.2f})",
                metadata={
                    "upper_band": round(upper_now, 4),
                    "middle_band": round(float(middle[-1]), 4),
                    "lower_band": round(lower_now, 4),
                    "pct_b": round(float(pct_b[-1]), 2),
                },
            )

        if close_prev < upper_prev and close_now >= upper_now:
            return Signal(
                action="sell",
                confidence=0.78,
                entry_price=Decimal(str(close_now)),
                reason=f"Bollinger upper band touch ({close_now:.2f} >= {upper_now:.2f})",
                metadata={
                    "upper_band": round(upper_now, 4),
                    "middle_band": round(float(middle[-1]), 4),
                    "lower_band": round(lower_now, 4),
                    "pct_b": round(float(pct_b[-1]), 2),
                },
            )

        return None


class GridStrategy(BaseStrategy):
    """简化网格均值回归策略"""

    name = "网格策略"
    strategy_type = "grid"

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self._last_grid_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"last_grid_index": self._last_grid_index}

    def from_dict(self, data: dict[str, Any]) -> None:
        value = data.get("last_grid_index")
        self._last_grid_index = int(value) if value is not None else None

    async def analyze(self, klines: list[dict]) -> Signal | None:
        grid_count = max(2, int(self.params.get("gridCount", 10)))
        price_range_pct = max(0.5, float(self.params.get("priceRange", 10.0)))
        window = max(grid_count * 2, 20)
        if len(klines) < window:
            return None

        closes = [float(k["close"]) for k in klines[-window:]]
        current_price = closes[-1]
        anchor_price = sum(closes) / len(closes)
        band_half_span = anchor_price * (price_range_pct / 100)
        if band_half_span <= 0:
            return None

        grid_size = (band_half_span * 2) / grid_count
        if grid_size <= 0:
            return None

        relative_price = max(-band_half_span, min(band_half_span, current_price - anchor_price))
        grid_index = floor(relative_price / grid_size)

        if self._last_grid_index is None:
            self._last_grid_index = grid_index
            return None

        prev_index = self._last_grid_index
        self._last_grid_index = grid_index

        if grid_index < prev_index and grid_index <= -1:
            return Signal(
                action="buy",
                confidence=0.72,
                entry_price=Decimal(str(current_price)),
                reason=f"Grid buy at level {grid_index}",
                metadata={
                    "grid_index": grid_index,
                    "anchor_price": round(anchor_price, 4),
                    "grid_size": round(grid_size, 4),
                },
            )

        if grid_index > prev_index and grid_index >= 1:
            return Signal(
                action="sell",
                confidence=0.72,
                entry_price=Decimal(str(current_price)),
                reason=f"Grid sell at level {grid_index}",
                metadata={
                    "grid_index": grid_index,
                    "anchor_price": round(anchor_price, 4),
                    "grid_size": round(grid_size, 4),
                },
            )

        return None


class MartingaleStrategy(BaseStrategy):
    """简化马丁格尔策略"""

    name = "马丁格尔策略"
    strategy_type = "martingale"

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self._loss_streak = 0
        self._position_entry_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "loss_streak": self._loss_streak,
            "position_entry_price": self._position_entry_price,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        self._loss_streak = int(data.get("loss_streak", 0))
        entry = data.get("position_entry_price")
        self._position_entry_price = float(entry) if entry is not None else None

    async def analyze(self, klines: list[dict]) -> Signal | None:
        if len(klines) < 6:
            return None

        multiplier = max(1.0, float(self.params.get("multiplier", 2.0)))
        max_losses = max(1, int(self.params.get("maxLosses", 5)))
        # initialInvestment 是 seed_data 模板字段(每次开仓 USDT 基础值),
        # 之前死参数 — 策略不读,所以 multiplier 算的 scale 没传给引擎,
        # 用户改 1.5x/2.0x 完全没区别。现在 invest_amount = init × scale
        # 真实反映"亏损后翻倍下单"语义。
        initial_invest = float(self.params.get("initialInvestment", 100))
        closes = [float(k["close"]) for k in klines[-6:]]
        current_price = closes[-1]

        falling_streak = closes[-1] < closes[-2] < closes[-3]
        rising_streak = closes[-1] > closes[-2] > closes[-3]

        if self._position_entry_price is None and falling_streak:
            scale = min(multiplier**self._loss_streak, multiplier**max_losses)
            invest_amount = initial_invest * scale
            self._position_entry_price = current_price
            return Signal(
                action="buy",
                confidence=min(0.9, 0.65 + self._loss_streak * 0.05),
                entry_price=Decimal(str(current_price)),
                reason=f"Martingale entry after drawdown streak={self._loss_streak}",
                metadata={
                    "martingale_step": self._loss_streak,
                    "position_scale": round(scale, 4),
                    "invest_amount": round(invest_amount, 2),
                },
            )

        if self._position_entry_price is None:
            return None

        take_profit_price = self._position_entry_price * 1.01
        stop_add_price = self._position_entry_price * 0.99

        if current_price >= take_profit_price or rising_streak:
            pnl_positive = current_price >= self._position_entry_price
            self._loss_streak = 0 if pnl_positive else min(self._loss_streak + 1, max_losses)
            self._position_entry_price = None
            return Signal(
                action="sell",
                confidence=0.75,
                entry_price=Decimal(str(current_price)),
                reason="Martingale exit on rebound",
                metadata={"martingale_step": self._loss_streak},
            )

        if current_price <= stop_add_price and self._loss_streak < max_losses:
            self._loss_streak += 1
            self._position_entry_price = current_price
            scale = min(multiplier**self._loss_streak, multiplier**max_losses)
            invest_amount = initial_invest * scale
            return Signal(
                action="buy",
                confidence=min(0.92, 0.68 + self._loss_streak * 0.05),
                entry_price=Decimal(str(current_price)),
                reason=f"Martingale add step={self._loss_streak}",
                metadata={
                    "martingale_step": self._loss_streak,
                    "position_scale": round(scale, 4),
                    "invest_amount": round(invest_amount, 2),
                },
            )

        return None


def get_strategy(strategy_type: str, config: StrategyConfig) -> BaseStrategy:
    """策略工厂"""
    if strategy_type == "ma":
        return MAStrategy(config)
    elif strategy_type == "rsi":
        return RSIStrategy(config)
    elif strategy_type == "bollinger":
        return BollingerStrategy(config)
    elif strategy_type == "grid":
        return GridStrategy(config)
    elif strategy_type == "martingale":
        return MartingaleStrategy(config)
    elif strategy_type == "rule":
        from app.core.rule_engine import RuleStrategy

        return RuleStrategy(config)
    elif strategy_type == "rsi_layered":
        from app.core.strategies.rsi_layered import RsiLayeredStrategy

        return RsiLayeredStrategy(config)
    elif strategy_type == "dca":
        from app.core.strategies.dca import DCAStrategy

        return DCAStrategy(config)
    elif strategy_type == "multi_symbol":
        from app.core.strategies.multi_symbol import MultiSymbolStrategy

        return MultiSymbolStrategy(config)
    else:
        raise ValueError(f"不支持的策略类型: {strategy_type}")
