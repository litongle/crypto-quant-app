"""
DCA（定投）策略实现 - P2-10

定期定额投资策略：
- 按固定时间间隔（天/周/月）或价格间隔自动买入
- 支持动态调整定投金额（基于价格偏离度）
- 支持止盈平仓
"""

import logging
from decimal import Decimal
from typing import Any

from app.core.strategy_engine import BaseStrategy, Signal, StrategyConfig

logger = logging.getLogger(__name__)


class DCAStrategy(BaseStrategy):
    """定投策略

    核心逻辑：
    1. 每隔 N 根 K 线，自动生成买入信号
    2. 支持基于RSI的智能定投（RSI低时加大定投额）
    3. 达到止盈条件时平仓
    """

    name = "DCA 定投策略"
    strategy_type = "dca"

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        # 定投间隔（K线数，如1h K线间隔=24即每天定投一次）
        self.interval_candles = int(self.params.get("dca_interval_candles", 24))
        # 每次定投金额（USDT）
        self.invest_per_trade = Decimal(str(self.params.get("invest_per_trade", 100)))
        # 启用智能定投（基于RSI调整金额）
        self.smart_dca = bool(self.params.get("smart_dca", False))
        # 止盈比例（%）
        self.take_profit_pct = Decimal(str(self.params.get("take_profit_pct", 20)))
        # 止损比例（%）
        self.stop_loss_pct = Decimal(str(self.params.get("stop_loss_pct", 30)))
        # 内部计数器
        self._candle_count = 0
        self._in_position = False
        self._avg_entry_price: Decimal = Decimal("0")
        self._total_quantity: Decimal = Decimal("0")
        self._total_invested: Decimal = Decimal("0")
        self._last_signal_index = -1

    async def analyze(self, klines: list[dict]) -> Signal | None:
        if len(klines) < 50:
            return None

        current_price = Decimal(str(klines[-1]["close"]))
        kline_index = len(klines) - 1

        # 已有持仓时检查止盈止损
        if self._in_position and self._avg_entry_price > 0:
            profit_pct = (current_price - self._avg_entry_price) / self._avg_entry_price * 100

            # 止盈
            if profit_pct >= self.take_profit_pct:
                self._reset_state()
                return Signal(
                    action="sell",
                    confidence=1.0,
                    entry_price=current_price,
                    reason=f"DCA 止盈: +{float(profit_pct):.2f}%",
                    metadata={"intent": "take_profit", "direction": "long"},
                )

            # 止损
            if profit_pct <= -self.stop_loss_pct:
                self._reset_state()
                return Signal(
                    action="sell",
                    confidence=1.0,
                    entry_price=current_price,
                    reason=f"DCA 止损: {float(profit_pct):.2f}%",
                    metadata={"intent": "stop_loss", "direction": "long"},
                )

        # 检测是否需要定投（新K线出现 + 间隔足够）
        if kline_index > self._last_signal_index:
            self._candle_count += 1
            if self._candle_count >= self.interval_candles:
                self._candle_count = 0
                self._last_signal_index = kline_index

                # 计算定投金额
                invest_amount = self.invest_per_trade

                # 智能定投：RSI低时加大投入
                if self.smart_dca and len(klines) >= 14:
                    rsi = self._calc_rsi(klines, 14)
                    if rsi < 30:
                        invest_amount = invest_amount * Decimal("1.5")  # 超卖时买入150%
                    elif rsi > 70:
                        invest_amount = invest_amount * Decimal("0.5")  # 超买时减半

                entry_price = current_price
                quantity = invest_amount / entry_price

                # 更新平均成本
                if self._total_quantity > 0:
                    total_value = self._avg_entry_price * self._total_quantity + invest_amount
                    self._total_quantity += quantity
                    self._avg_entry_price = total_value / self._total_quantity
                else:
                    self._avg_entry_price = entry_price
                    self._total_quantity = quantity

                self._total_invested += invest_amount
                self._in_position = True

                return Signal(
                    action="buy",
                    confidence=0.9,
                    entry_price=current_price,
                    reason=(
                        f"DCA 定投: {float(invest_amount):.2f} USDT"
                        + (" [智能:RSI放大]" if invest_amount > self.invest_per_trade else "")
                        + (" [智能:RSI缩减]" if invest_amount < self.invest_per_trade else "")
                    ),
                    metadata={
                        "intent": "open",
                        "direction": "long",
                        "invest_amount": float(invest_amount),
                    },
                )

        return None

    def _calc_rsi(self, klines: list[dict], period: int = 14) -> float:
        """计算 RSI"""
        if len(klines) < period + 1:
            return 50.0
        gains = Decimal("0")
        losses = Decimal("0")
        for i in range(len(klines) - period, len(klines)):
            change = Decimal(str(klines[i]["close"])) - Decimal(str(klines[i - 1]["close"]))
            if change > 0:
                gains += change
            else:
                losses += abs(change)
        avg_gain = gains / period
        avg_loss = losses / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return float(100 - (100 / (1 + rs)))

    def _reset_state(self):
        self._in_position = False
        self._avg_entry_price = Decimal("0")
        self._total_quantity = Decimal("0")
        self._total_invested = Decimal("0")

    # Step 3: 状态持久化
    def to_dict(self) -> dict[str, Any]:
        return {
            "candle_count": self._candle_count,
            "in_position": self._in_position,
            "avg_entry_price": str(self._avg_entry_price),
            "total_quantity": str(self._total_quantity),
            "total_invested": str(self._total_invested),
            "last_signal_index": self._last_signal_index,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        self._candle_count = int(data.get("candle_count", 0))
        self._in_position = bool(data.get("in_position", False))
        self._avg_entry_price = Decimal(str(data.get("avg_entry_price", "0")))
        self._total_quantity = Decimal(str(data.get("total_quantity", "0")))
        self._total_invested = Decimal(str(data.get("total_invested", "0")))
        self._last_signal_index = int(data.get("last_signal_index", -1))
