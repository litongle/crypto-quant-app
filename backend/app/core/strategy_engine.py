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
    timestamp: datetime = datetime.now(timezone.utc)
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
        # 参数：短周期和长周期均线窗口，默认 5 和 20
        short_window = self.params.get("short_window", 5)
        long_window = self.params.get("long_window", 20)

        if len(klines) < long_window:
            return None

        # 提取收盘价
        closes = [Decimal(str(k["close"])) for k in klines]

        def calc_ma(data: list[Decimal], window: int) -> Decimal | None:
            """计算简单移动平均"""
            if len(data) < window:
                return None
            return sum(data[-window:]) / window

        # 计算当前均线值
        short_ma = calc_ma(closes, short_window)
        long_ma = calc_ma(closes, long_window)

        if short_ma is None or long_ma is None:
            return None

        # 计算前一根K线的均线值（用于判断交叉）
        prev_closes = closes[:-1]
        prev_short_ma = calc_ma(prev_closes, short_window)
        prev_long_ma = calc_ma(prev_closes, long_window)

        if prev_short_ma is None or prev_long_ma is None:
            return None

        # 金叉：短均线上穿长均线 -> 买入信号
        if prev_short_ma <= prev_long_ma and short_ma > long_ma:
            return Signal(
                action="buy",
                confidence=0.8,
                entry_price=closes[-1],
                reason=f"MA Golden Cross (MA{short_window} crossed above MA{long_window})",
                metadata={"short_ma": float(short_ma), "long_ma": float(long_ma)},
            )

        # 死叉：短均线下穿长均线 -> 卖出信号
        if prev_short_ma >= prev_long_ma and short_ma < long_ma:
            return Signal(
                action="sell",
                confidence=0.8,
                entry_price=closes[-1],
                reason=f"MA Death Cross (MA{short_window} crossed below MA{long_window})",
                metadata={"short_ma": float(short_ma), "long_ma": float(long_ma)},
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

        closes = [float(k["close"]) for k in klines]

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


def get_strategy(strategy_type: str, config: StrategyConfig) -> BaseStrategy:
    """策略工厂"""
    if strategy_type == "ma":
        return MAStrategy(config)
    elif strategy_type == "rsi":
        return RSIStrategy(config)
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
