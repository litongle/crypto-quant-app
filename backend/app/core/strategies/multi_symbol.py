"""
多币种/跨币种相关性策略 - P2-11

支持:
- 一对多: 一个策略监听多个交易对（如 BTC 信号触发买 ETH）
- 配对交易: 两个高度相关币种价差回归
- 跨币种信号联动
"""

import logging
from decimal import Decimal
from typing import Any

from app.core.strategy_engine import BaseStrategy, Signal, StrategyConfig

logger = logging.getLogger(__name__)


class MultiSymbolStrategy(BaseStrategy):
    """多币种策略

    核心逻辑：
    1. 监听主交易对（leader）的信号
    2. 在主交易对方向明确时，联动操作从交易对（followers）
    3. 配对交易：计算两个币种价差，价差回归时开仓

    参数：
    - leader_symbol: 主交易对
    - follower_symbols: 跟随交易对列表
    - correlation_threshold: 相关性阈值
    - mode: "leader_follow" | "pair_trading"
    """

    name = "多币种联动策略"
    strategy_type = "multi_symbol"

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.mode = self.params.get("mode", "leader_follow")
        self.leader_symbol = self.params.get("leader_symbol", config.symbol)
        self.follower_symbols = self.params.get("follower_symbols", [])
        self.confidence_threshold = float(self.params.get("confidence_threshold", 0.6))
        # 配对交易参数
        self.pair_symbol = self.params.get("pair_symbol", "")
        self.entry_zscore = float(self.params.get("entry_zscore", 2.0))
        self.exit_zscore = float(self.params.get("exit_zscore", 0.5))
        self.lookback = int(self.params.get("lookback", 100))

        # 状态
        self._in_position = False
        self._position_direction: str | None = None
        self._mean_spread: float = 0
        self._std_spread: float = 0
        self._spread_history: list[float] = []

    async def analyze(self, klines: list[dict]) -> Signal | None:
        """分析K线并生成信号

        注意: klines 是当前 config.symbol 的数据。
        多币种策略需要额外获取其他交易对数据，实际运行中需要修改 runner。
        此处仅提供策略逻辑框架。
        """
        if len(klines) < 50:
            return None

        current_price = Decimal(str(klines[-1]["close"]))

        if self.mode == "leader_follow":
            return await self._analyze_leader_follow(klines, current_price)
        elif self.mode == "pair_trading":
            return await self._analyze_pair_trading(klines, current_price)

        return None

    async def _analyze_leader_follow(
        self,
        klines: list[dict],
        current_price: Decimal,
    ) -> Signal | None:
        """Leader-Follow 模式: 主币种信号联动从币种"""
        # 这里对主交易对做简单趋势判断
        short_ma = self._calc_ma(klines, 10)
        long_ma = self._calc_ma(klines, 30)

        if short_ma is None or long_ma is None:
            return None

        # 金叉
        if short_ma > long_ma and not self._in_position:
            self._in_position = True
            self._position_direction = "long"
            confidence = min(1.0, (short_ma - long_ma) / long_ma * 100 + 0.5)

            follower_info = ""
            if self.follower_symbols:
                follower_info = f" 联动: {', '.join(self.follower_symbols)}"

            return Signal(
                action="buy",
                confidence=confidence,
                entry_price=current_price,
                reason=f"Leader-Follow 做多 @ {self.leader_symbol}{follower_info}",
                metadata={
                    "intent": "open",
                    "direction": "long",
                    "leader_symbol": self.leader_symbol,
                    "follower_symbols": self.follower_symbols,
                    "mode": self.mode,
                },
            )

        # 死叉
        elif short_ma < long_ma and self._in_position and self._position_direction == "long":
            self._in_position = False
            self._position_direction = None
            return Signal(
                action="sell",
                confidence=0.8,
                entry_price=current_price,
                reason="Leader-Follow 平多",
                metadata={"intent": "take_profit", "direction": "long", "mode": self.mode},
            )

        return None

    async def _analyze_pair_trading(
        self,
        klines: list[dict],
        current_price: Decimal,
    ) -> Signal | None:
        """配对交易模式: 价差回归

        假设我们已经有配对币种的价格数据（通过 metadata 传入），
        计算价差的 z-score，在极端值时开仓。
        """
        # 配对交易需要两个币种的价格数据
        # 实际运行时，_run_loop 需要预合并两个币种的K线
        pair_prices = self.params.get("pair_prices", [])
        if not pair_prices or len(pair_prices) != len(klines):
            return None

        # 计算价差（以比例形式）
        spreads = []
        for i in range(min(len(klines), self.lookback)):
            price_a = float(klines[-(i + 1)]["close"])
            price_b = pair_prices[min(i, len(pair_prices) - 1)]
            if price_b > 0:
                spreads.append(price_a / price_b)

        if len(spreads) < 20:
            return None

        spreads.reverse()
        current_spread = spreads[-1]
        self._mean_spread = sum(spreads) / len(spreads)
        variance = sum((s - self._mean_spread) ** 2 for s in spreads) / len(spreads)
        self._std_spread = variance**0.5

        if self._std_spread == 0:
            return None

        zscore = (current_spread - self._mean_spread) / self._std_spread

        # 价差过大 → 回归交易（卖主买从）
        if zscore > self.entry_zscore and not self._in_position:
            self._in_position = True
            self._position_direction = "short_spread"
            return Signal(
                action="sell",
                confidence=min(1.0, abs(zscore) / (self.entry_zscore * 2)),
                entry_price=current_price,
                reason=f"配对交易: 价差 z={zscore:.2f} > 阈值 {self.entry_zscore}, 做空价差",
                metadata={
                    "intent": "open",
                    "direction": "short",
                    "mode": self.mode,
                    "pair": self.pair_symbol,
                },
            )

        # 价差过小 → 回归交易（买主卖从）
        if zscore < -self.entry_zscore and not self._in_position:
            self._in_position = True
            self._position_direction = "long_spread"
            return Signal(
                action="buy",
                confidence=min(1.0, abs(zscore) / (self.entry_zscore * 2)),
                entry_price=current_price,
                reason=f"配对交易: 价差 z={zscore:.2f} < 阈值 {-self.entry_zscore}, 做多价差",
                metadata={
                    "intent": "open",
                    "direction": "long",
                    "mode": self.mode,
                    "pair": self.pair_symbol,
                },
            )

        # 价差回归 → 平仓
        if self._in_position and abs(zscore) < self.exit_zscore:
            self._in_position = False
            direction = self._position_direction
            self._position_direction = None
            return Signal(
                action="sell" if direction == "long_spread" else "buy",
                confidence=0.9,
                entry_price=current_price,
                reason=f"配对交易: 价差回归 z={zscore:.2f}, 平仓",
                metadata={
                    "intent": "take_profit",
                    "direction": "long" if direction == "long_spread" else "short",
                },
            )

        return None

    def _calc_ma(self, klines: list[dict], period: int) -> float | None:
        """计算移动平均"""
        if len(klines) < period:
            return None
        closes = [Decimal(str(k["close"])) for k in klines[-period:]]
        return float(sum(closes) / len(closes))

    # Step 3: 状态持久化
    def to_dict(self) -> dict[str, Any]:
        return {
            "in_position": self._in_position,
            "position_direction": self._position_direction,
            "mean_spread": self._mean_spread,
            "std_spread": self._std_spread,
            "spread_history": self._spread_history[-50:],  # 只保存最近50个
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        self._in_position = bool(data.get("in_position", False))
        self._position_direction = data.get("position_direction")
        self._mean_spread = float(data.get("mean_spread", 0))
        self._std_spread = float(data.get("std_spread", 0))
        self._spread_history = data.get("spread_history", [])
