"""
策略引擎基类及具体策略实现
"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class StrategyConfig(BaseModel):
    """策略配置"""
    symbol: str
    exchange: str
    direction: Literal["long", "short", "both"] = "both"
    params: dict[str, Any] = {}
    risk_params: dict[str, Any] = {}


class Signal(BaseModel):
    """策略生成的信号"""
    action: Literal["buy", "sell", "hold"]
    confidence: float = 1.0
    entry_price: Decimal | None = None
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    reason: str | None = None
    timestamp: datetime = datetime.now(timezone.utc)


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


class MAStrategy(BaseStrategy):
    """移动平均线策略"""
    name = "均线交叉策略"
    strategy_type = "ma"

    async def analyze(self, klines: list[dict]) -> Signal | None:
        if len(klines) < 20:
            return None
        
        # 简单逻辑：最后两根K线的收盘价
        last_close = Decimal(str(klines[-1]["close"]))
        prev_close = Decimal(str(klines[-2]["close"]))
        
        # 模拟信号逻辑
        if last_close > prev_close:
            return Signal(action="buy", confidence=0.8, entry_price=last_close, reason="Price up")
        elif last_close < prev_close:
            return Signal(action="sell", confidence=0.8, entry_price=last_close, reason="Price down")
        
        return None


class RSIStrategy(BaseStrategy):
    """RSI 策略"""
    name = "RSI 超买超卖策略"
    strategy_type = "rsi"

    async def analyze(self, klines: list[dict]) -> Signal | None:
        # 简化的 RSI 逻辑
        return None


def get_strategy(strategy_type: str, config: StrategyConfig) -> BaseStrategy:
    """策略工厂"""
    if strategy_type == "ma":
        return MAStrategy(config)
    elif strategy_type == "rsi":
        return RSIStrategy(config)
    elif strategy_type == "rule":
        from app.core.rule_engine import RuleStrategy
        return RuleStrategy(config)
    else:
        raise ValueError(f"不支持的策略类型: {strategy_type}")
