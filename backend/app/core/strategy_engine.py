"""
策略引擎框架
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import numpy as np


@dataclass
class Signal:
    """交易信号"""
    action: str  # buy, sell, close
    confidence: float  # 0.0 - 1.0
    entry_price: Decimal | None
    stop_loss_price: Decimal | None
    take_profit_price: Decimal | None
    reason: str
    timestamp: datetime


@dataclass
class StrategyConfig:
    """策略配置"""
    symbol: str
    exchange: str
    direction: str  # long, short, both
    params: dict[str, Any]
    risk_params: dict[str, Any]


class BaseStrategy(ABC):
    """策略基类"""

    name: str = "BaseStrategy"
    strategy_type: str = "base"

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.klines: list[dict] = []

    @abstractmethod
    async def analyze(self, klines: list[dict]) -> Signal | None:
        """分析K线数据，生成交易信号"""
        pass

    def calculate_pnl(
        self, entry_price: Decimal, current_price: Decimal, side: str
    ) -> tuple[Decimal, Decimal]:
        """计算盈亏"""
        if side == "long":
            pnl = current_price - entry_price
            pnl_percent = (pnl / entry_price) * 100
        else:
            pnl = entry_price - current_price
            pnl_percent = (pnl / entry_price) * 100
        return pnl, pnl_percent

    def check_stop_loss(self, current_price: Decimal, entry_price: Decimal, side: str) -> bool:
        """检查是否触发止损"""
        sl_percent = self.config.risk_params.get("stop_loss_percent", 2.0)
        if side == "long":
            loss_percent = ((entry_price - current_price) / entry_price) * 100
        else:
            loss_percent = ((current_price - entry_price) / entry_price) * 100
        return loss_percent >= sl_percent

    def _sma(self, data: np.ndarray, period: int) -> np.ndarray:
        """简单移动平均"""
        return np.convolve(data, np.ones(period) / period, mode="valid")


class MAStrategy(BaseStrategy):
    """双均线策略"""

    name = "双均线策略"
    strategy_type = "ma"

    async def analyze(self, klines: list[dict]) -> Signal | None:
        """双均线交叉分析"""
        if len(klines) < 50:
            return None

        closes = np.array([float(k["close"]) for k in klines])
        
        fast_period = self.config.params.get("fast_period", 10)
        slow_period = self.config.params.get("slow_period", 30)
        
        fast_ma = self._sma(closes, fast_period)
        slow_ma = self._sma(closes, slow_period)
        
        if len(fast_ma) < 2 or len(slow_ma) < 2:
            return None
        
        prev_fast = fast_ma[-2]
        prev_slow = slow_ma[-2]
        curr_fast = fast_ma[-1]
        curr_slow = slow_ma[-1]

        current_price = Decimal(str(closes[-1]))
        
        # 金叉买入
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            if self.config.direction in ["long", "both"]:
                return Signal(
                    action="buy",
                    confidence=0.7,
                    entry_price=current_price,
                    stop_loss_price=current_price * Decimal("0.98"),
                    take_profit_price=current_price * Decimal("1.05"),
                    reason=f"MA{fast_period}上穿MA{slow_period}",
                    timestamp=datetime.utcnow(),
                )
        
        # 死叉卖出
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            if self.config.direction in ["short", "both"]:
                return Signal(
                    action="sell",
                    confidence=0.7,
                    entry_price=current_price,
                    stop_loss_price=current_price * Decimal("1.02"),
                    take_profit_price=current_price * Decimal("0.95"),
                    reason=f"MA{fast_period}下穿MA{slow_period}",
                    timestamp=datetime.utcnow(),
                )

        return None


class RSIStrategy(BaseStrategy):
    """RSI 超买超卖策略"""

    name = "RSI 策略"
    strategy_type = "rsi"

    async def analyze(self, klines: list[dict]) -> Signal | None:
        """RSI 分析"""
        period = self.config.params.get("period", 14)
        oversold = self.config.params.get("oversold", 30)
        overbought = self.config.params.get("overbought", 70)

        if len(klines) < period + 1:
            return None

        closes = np.array([float(k["close"]) for k in klines])
        rsi = self._rsi(closes, period)
        
        if rsi[-1] < oversold and self.config.direction in ["long", "both"]:
            return Signal(
                action="buy",
                confidence=0.8,
                entry_price=Decimal(str(closes[-1])),
                stop_loss_price=Decimal(str(closes[-1])) * Decimal("0.97"),
                take_profit_price=Decimal(str(closes[-1])) * Decimal("1.06"),
                reason=f"RSI 超卖 ({rsi[-1]:.1f})",
                timestamp=datetime.utcnow(),
            )
        
        if rsi[-1] > overbought and self.config.direction in ["short", "both"]:
            return Signal(
                action="sell",
                confidence=0.8,
                entry_price=Decimal(str(closes[-1])),
                stop_loss_price=Decimal(str(closes[-1])) * Decimal("1.03"),
                take_profit_price=Decimal(str(closes[-1])) * Decimal("0.94"),
                reason=f"RSI 超买 ({rsi[-1]:.1f})",
                timestamp=datetime.utcnow(),
            )

        return None

    def _rsi(self, data: np.ndarray, period: int) -> np.ndarray:
        """RSI 计算"""
        deltas = np.diff(data)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.convolve(gains, np.ones(period) / period, mode="valid")
        avg_loss = np.convolve(losses, np.ones(period) / period, mode="valid")
        
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return rsi


class BollingerStrategy(BaseStrategy):
    """布林带策略"""

    name = "布林带策略"
    strategy_type = "bollinger"

    async def analyze(self, klines: list[dict]) -> Signal | None:
        """布林带分析"""
        period = self.config.params.get("period", 20)
        std_dev = self.config.params.get("std_dev", 2.0)

        if len(klines) < period:
            return None

        closes = np.array([float(k["close"]) for k in klines])
        upper, middle, lower = self._bollinger_bands(closes, period, std_dev)

        current_price = closes[-1]
        
        if current_price <= lower[-1] and self.config.direction in ["long", "both"]:
            return Signal(
                action="buy",
                confidence=0.75,
                entry_price=Decimal(str(current_price)),
                stop_loss_price=Decimal(str(lower[-1] * 0.98)),
                take_profit_price=Decimal(str(middle[-1])),
                reason="价格触及布林带下轨",
                timestamp=datetime.utcnow(),
            )
        
        if current_price >= upper[-1] and self.config.direction in ["short", "both"]:
            return Signal(
                action="sell",
                confidence=0.75,
                entry_price=Decimal(str(current_price)),
                stop_loss_price=Decimal(str(upper[-1] * 1.02)),
                take_profit_price=Decimal(str(middle[-1])),
                reason="价格触及布林带上轨",
                timestamp=datetime.utcnow(),
            )

        return None

    def _bollinger_bands(
        self, data: np.ndarray, period: int, std_dev: float
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """布林带计算"""
        middle = np.convolve(data, np.ones(period) / period, mode="valid")
        std = np.array([np.std(data[i:i+period]) for i in range(len(data) - period + 1)])
        upper = middle + std * std_dev
        lower = middle - std * std_dev
        return upper, middle, lower


class GridStrategy(BaseStrategy):
    """网格交易策略"""

    name = "网格策略"
    strategy_type = "grid"

    async def analyze(self, klines: list[dict]) -> Signal | None:
        """网格策略"""
        grid_count = self.config.params.get("grid_count", 5)
        grid_spacing = self.config.params.get("grid_spacing", 0.02)

        if len(klines) < 50:
            return None

        closes = np.array([float(k["close"]) for k in klines])
        current_price = closes[-1]
        
        recent_prices = closes[-50:]
        high = max(recent_prices)
        low = min(recent_prices)
        
        price_range = high - low
        grid_step = price_range / grid_count
        
        for i in range(1, grid_count):
            grid_price = low + grid_step * i
            if abs(current_price - grid_price) / grid_price < 0.005:
                if current_price > grid_price and self.config.direction in ["long", "both"]:
                    return Signal(
                        action="buy",
                        confidence=0.6,
                        entry_price=Decimal(str(grid_price)),
                        stop_loss_price=Decimal(str(low * 0.95)),
                        take_profit_price=Decimal(str(grid_price + grid_step)),
                        reason=f"网格买入 {i}/{grid_count}",
                        timestamp=datetime.utcnow(),
                    )
        
        return None


def get_strategy(strategy_type: str, config: StrategyConfig) -> BaseStrategy:
    """策略工厂"""
    strategies = {
        "ma": MAStrategy,
        "rsi": RSIStrategy,
        "bollinger": BollingerStrategy,
        "grid": GridStrategy,
    }
    strategy_class = strategies.get(strategy_type.lower())
    if not strategy_class:
        raise ValueError(f"不支持的策略类型: {strategy_type}")
    return strategy_class(config)
