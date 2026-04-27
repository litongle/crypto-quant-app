"""
RSI 分层极值追踪策略

移植自 gc/app/strategy/rsi_layered.py，适配 BaseStrategy 接口。

核心思想:
  1. 监控 RSI 进入多头/空头分层阈值区间(超卖/超买的三层)
  2. 在区间内持续追踪 RSI 极值
  3. 当 RSI 从极值回撤指定点数时触发交易信号
  4. 持仓中支持加仓、分层浮动止盈、固定止损、超时平仓、反手交易、冷却期

状态机:
  monitoring → long/short(开仓) → cooling(平仓后) → monitoring

持仓状态由策略自身维护(基于自己发出的信号),Step 2 起将由 runner
注入实际成交结果以应对滑点/部分成交。
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from enum import IntEnum
from typing import Any

import numpy as np

from app.core.indicators import calc_rsi
from app.core.strategy_engine import BaseStrategy, Signal, StrategyConfig

logger = logging.getLogger(__name__)


class RsiLevel(IntEnum):
    NONE = 0
    LEVEL1 = 1
    LEVEL2 = 2
    LEVEL3 = 3


# 默认参数 — 可由 config.params 覆盖
DEFAULTS: dict[str, Any] = {
    "rsi_period": 14,
    # 多头阈值(RSI 越低越超卖,触发做多追踪)
    "long_levels": [30, 25, 20],
    # 空头阈值(RSI 越高越超买,触发做空追踪)
    "short_levels": [70, 75, 80],
    "retracement_points": 2.0,
    "max_additional_positions": 4,
    # 单位为价格点数(基础货币计价,如 USDT)
    "fixed_stop_loss_points": 6.0,
    # 分层浮动止盈: [(窗口K线数, 回撤点数, 最小盈利点数), ...]
    "profit_taking_config": [
        [10, 3.0, 2.0],
        [30, 5.0, 3.0],
        [60, 10.0, 5.0],
    ],
    "max_holding_candles": 60,
    "cooling_candles": 3,
}


class RsiLayeredStrategy(BaseStrategy):
    """RSI 分层极值追踪策略"""

    name = "RSI 分层极值追踪"
    strategy_type = "rsi_layered"

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        p = {**DEFAULTS, **(config.params or {})}

        self.rsi_period: int = int(p["rsi_period"])
        self.long_levels: list[float] = [float(x) for x in p["long_levels"]]
        self.short_levels: list[float] = [float(x) for x in p["short_levels"]]
        self.retracement_points: float = float(p["retracement_points"])
        self.max_additional_positions: int = int(p["max_additional_positions"])
        self.fixed_stop_loss_points: float = float(p["fixed_stop_loss_points"])
        self.profit_taking_config: list[tuple[int, float, float]] = [
            (int(w), float(r), float(m)) for w, r, m in p["profit_taking_config"]
        ]
        self.max_holding_candles: int = int(p["max_holding_candles"])
        self.cooling_candles: int = int(p["cooling_candles"])

        # ── 运行时状态 ──
        self._mode: str = "monitoring"  # monitoring / long / short / cooling
        self._cooling_count: int = 0

        # 多头追踪
        self._long_monitoring: bool = False
        self._long_extreme_value: float | None = None
        self._long_extreme_time: datetime | None = None
        self._long_level: RsiLevel = RsiLevel.NONE

        # 空头追踪
        self._short_monitoring: bool = False
        self._short_extreme_value: float | None = None
        self._short_extreme_time: datetime | None = None
        self._short_level: RsiLevel = RsiLevel.NONE

        # 持仓追踪
        self._position_dir: str | None = None  # "long" / "short" / None
        self._entry_price: float | None = None
        self._holding_periods: int = 0
        self._max_profit: float = 0.0
        self._additional_positions_count: int = 0

        # 防止同根 K 线重复触发
        self._last_kline_ts: int | None = None

    # ── 入口 ──────────────────────────────────────────────

    async def analyze(self, klines: list[dict]) -> Signal | None:
        """处理最新一根 K 线,返回信号(无信号返回 None)"""
        if len(klines) < self.rsi_period + 1:
            return None

        latest = klines[-1]
        ts = int(latest.get("timestamp") or 0)
        if self._last_kline_ts is not None and ts != 0 and ts <= self._last_kline_ts:
            return None
        self._last_kline_ts = ts

        closes = np.array([float(k["close"]) for k in klines], dtype=np.float64)
        rsi_arr = calc_rsi(closes, self.rsi_period)
        if len(rsi_arr) == 0 or np.isnan(rsi_arr[-1]):
            return None

        current_rsi = float(rsi_arr[-1])
        kline_time = _ts_to_dt(ts)

        long_lvl, short_lvl = self._check_rsi_level(current_rsi)
        self._update_extreme_values(current_rsi, kline_time, long_lvl, short_lvl)

        if self._position_dir is not None:
            self._holding_periods += 1

        if self._mode == "monitoring":
            return self._on_monitoring(current_rsi, latest)
        if self._mode == "long":
            return self._on_long(current_rsi, latest)
        if self._mode == "short":
            return self._on_short(current_rsi, latest)
        if self._mode == "cooling":
            return self._on_cooling()
        return None

    # ── RSI 分层与极值追踪 ─────────────────────────────────

    def _check_rsi_level(self, rsi: float) -> tuple[RsiLevel, RsiLevel]:
        long_lvl = RsiLevel.NONE
        if rsi <= self.long_levels[0]:
            long_lvl = RsiLevel.LEVEL1
            if rsi <= self.long_levels[1]:
                long_lvl = RsiLevel.LEVEL2
                if rsi <= self.long_levels[2]:
                    long_lvl = RsiLevel.LEVEL3

        short_lvl = RsiLevel.NONE
        if rsi >= self.short_levels[0]:
            short_lvl = RsiLevel.LEVEL1
            if rsi >= self.short_levels[1]:
                short_lvl = RsiLevel.LEVEL2
                if rsi >= self.short_levels[2]:
                    short_lvl = RsiLevel.LEVEL3

        return long_lvl, short_lvl

    def _update_extreme_values(
        self,
        rsi: float,
        ts: datetime,
        long_lvl: RsiLevel,
        short_lvl: RsiLevel,
    ) -> None:
        # 多头追最低
        if long_lvl != RsiLevel.NONE:
            if not self._long_monitoring:
                self._long_monitoring = True
                self._long_extreme_value = rsi
                self._long_extreme_time = ts
                self._long_level = long_lvl
            elif self._long_extreme_value is None or rsi < self._long_extreme_value:
                self._long_extreme_value = rsi
                self._long_extreme_time = ts
                if long_lvl > self._long_level:
                    self._long_level = long_lvl

        # 空头追最高
        if short_lvl != RsiLevel.NONE:
            if not self._short_monitoring:
                self._short_monitoring = True
                self._short_extreme_value = rsi
                self._short_extreme_time = ts
                self._short_level = short_lvl
            elif self._short_extreme_value is None or rsi > self._short_extreme_value:
                self._short_extreme_value = rsi
                self._short_extreme_time = ts
                if short_lvl > self._short_level:
                    self._short_level = short_lvl

    def _check_retracement(self, rsi: float) -> tuple[bool, bool]:
        long_signal = False
        short_signal = False
        if self._long_monitoring and self._long_extreme_value is not None:
            if rsi - self._long_extreme_value >= self.retracement_points:
                long_signal = True
        if self._short_monitoring and self._short_extreme_value is not None:
            if self._short_extreme_value - rsi >= self.retracement_points:
                short_signal = True
        return long_signal, short_signal

    def _reset_long_tracking(self) -> None:
        self._long_monitoring = False
        self._long_extreme_value = None
        self._long_extreme_time = None
        self._long_level = RsiLevel.NONE

    def _reset_short_tracking(self) -> None:
        self._short_monitoring = False
        self._short_extreme_value = None
        self._short_extreme_time = None
        self._short_level = RsiLevel.NONE

    # ── 状态机分发 ────────────────────────────────────────

    def _on_monitoring(self, rsi: float, kline: dict) -> Signal | None:
        long_signal, short_signal = self._check_retracement(rsi)
        allowed = self.config.direction

        if long_signal and allowed in ("long", "both"):
            self._open_position("long", kline)
            self._reset_long_tracking()
            return self._make_signal(
                action="buy",
                kline=kline,
                intent="open",
                direction="long",
                reason=f"RSI_LONG_OPEN rsi={rsi:.2f}",
            )

        if short_signal and allowed in ("short", "both"):
            self._open_position("short", kline)
            self._reset_short_tracking()
            return self._make_signal(
                action="sell",
                kline=kline,
                intent="open",
                direction="short",
                reason=f"RSI_SHORT_OPEN rsi={rsi:.2f}",
            )
        return None

    def _on_long(self, rsi: float, kline: dict) -> Signal | None:
        _, short_signal = self._check_retracement(rsi)

        # 反手: 持仓超时 + 反向回撤 + 方向许可
        if (
            self._holding_periods >= self.max_holding_candles
            and short_signal
            and self.config.direction in ("short", "both")
        ):
            self._close_position()
            self._open_position("short", kline)
            self._reset_short_tracking()
            return self._make_signal(
                action="sell",
                kline=kline,
                intent="reverse",
                direction="short",
                reason=f"RSI_REVERSE_LONG_TO_SHORT rsi={rsi:.2f}",
            )

        if self._should_take_profit(kline):
            return self._close_signal_for(
                "long", kline, "take_profit", f"RSI_TAKE_PROFIT_LONG rsi={rsi:.2f}"
            )
        if self._should_stop_loss(kline):
            return self._close_signal_for(
                "long", kline, "stop_loss", f"RSI_STOP_LOSS_LONG rsi={rsi:.2f}"
            )
        if self._should_add_position("long", rsi):
            self._additional_positions_count += 1
            self._reset_long_tracking()
            return self._make_signal(
                action="buy",
                kline=kline,
                intent="add",
                direction="long",
                reason=f"RSI_LONG_ADD rsi={rsi:.2f} count={self._additional_positions_count}",
            )
        if self._holding_periods >= self.max_holding_candles:
            return self._close_signal_for(
                "long", kline, "timeout",
                f"RSI_TIMEOUT_LONG holding={self._holding_periods}",
            )
        return None

    def _on_short(self, rsi: float, kline: dict) -> Signal | None:
        long_signal, _ = self._check_retracement(rsi)

        if (
            self._holding_periods >= self.max_holding_candles
            and long_signal
            and self.config.direction in ("long", "both")
        ):
            self._close_position()
            self._open_position("long", kline)
            self._reset_long_tracking()
            return self._make_signal(
                action="buy",
                kline=kline,
                intent="reverse",
                direction="long",
                reason=f"RSI_REVERSE_SHORT_TO_LONG rsi={rsi:.2f}",
            )

        if self._should_take_profit(kline):
            return self._close_signal_for(
                "short", kline, "take_profit", f"RSI_TAKE_PROFIT_SHORT rsi={rsi:.2f}"
            )
        if self._should_stop_loss(kline):
            return self._close_signal_for(
                "short", kline, "stop_loss", f"RSI_STOP_LOSS_SHORT rsi={rsi:.2f}"
            )
        if self._should_add_position("short", rsi):
            self._additional_positions_count += 1
            self._reset_short_tracking()
            return self._make_signal(
                action="sell",
                kline=kline,
                intent="add",
                direction="short",
                reason=f"RSI_SHORT_ADD rsi={rsi:.2f} count={self._additional_positions_count}",
            )
        if self._holding_periods >= self.max_holding_candles:
            return self._close_signal_for(
                "short", kline, "timeout",
                f"RSI_TIMEOUT_SHORT holding={self._holding_periods}",
            )
        return None

    def _on_cooling(self) -> Signal | None:
        self._cooling_count += 1
        if self._cooling_count >= self.cooling_candles:
            self._mode = "monitoring"
            self._cooling_count = 0
        return None

    # ── 持仓决策 ──────────────────────────────────────────

    def _should_take_profit(self, kline: dict) -> bool:
        """分层浮动止盈: 达到窗口后,最大浮盈回撤超阈值 + 保留最低盈利"""
        if self._position_dir is None or self._entry_price is None:
            return False
        current_pnl = self._unrealized_pnl(kline)
        if current_pnl <= 0:
            return False
        if current_pnl > self._max_profit:
            self._max_profit = current_pnl
        retracement = self._max_profit - current_pnl
        for window, retr_points, min_profit in self.profit_taking_config:
            if (
                self._holding_periods >= window
                and retracement >= retr_points
                and current_pnl >= min_profit
            ):
                return True
        return False

    def _should_stop_loss(self, kline: dict) -> bool:
        if self._position_dir is None:
            return False
        return self._unrealized_pnl(kline) <= -self.fixed_stop_loss_points

    def _should_add_position(self, direction: str, rsi: float) -> bool:
        if self._additional_positions_count >= self.max_additional_positions:
            return False
        long_sig, short_sig = self._check_retracement(rsi)
        return (direction == "long" and long_sig) or (direction == "short" and short_sig)

    def _unrealized_pnl(self, kline: dict) -> float:
        """以价格点数计的浮动盈亏"""
        if self._entry_price is None:
            return 0.0
        current = float(kline["close"])
        if self._position_dir == "long":
            return current - self._entry_price
        if self._position_dir == "short":
            return self._entry_price - current
        return 0.0

    # ── 持仓状态过渡 ──────────────────────────────────────

    def _open_position(self, direction: str, kline: dict) -> None:
        self._mode = direction
        self._position_dir = direction
        self._entry_price = float(kline["close"])
        self._holding_periods = 0
        self._max_profit = 0.0
        self._additional_positions_count = 0

    def _close_position(self) -> None:
        self._mode = "cooling"
        self._cooling_count = 0
        self._position_dir = None
        self._entry_price = None
        self._holding_periods = 0
        self._max_profit = 0.0
        self._additional_positions_count = 0

    def _close_signal_for(
        self, dir_: str, kline: dict, kind: str, reason: str
    ) -> Signal:
        # 多头平仓 → sell;空头平仓 → buy
        action = "sell" if dir_ == "long" else "buy"
        self._close_position()
        return self._make_signal(
            action=action,
            kline=kline,
            intent=kind,
            direction=dir_,
            reason=reason,
        )

    def _make_signal(
        self,
        *,
        action: str,
        kline: dict,
        intent: str,
        direction: str,
        reason: str,
    ) -> Signal:
        return Signal(
            action=action,  # type: ignore[arg-type]
            confidence=0.7,
            entry_price=Decimal(str(kline["close"])),
            reason=reason,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "intent": intent,
                "direction": direction,
                "strategy": self.strategy_type,
            },
        )

    # ── 状态序列化(重启不丢仓位) ───────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self._mode,
            "cooling_count": self._cooling_count,
            "long_monitoring": self._long_monitoring,
            "long_extreme_value": self._long_extreme_value,
            "long_extreme_time": (
                self._long_extreme_time.isoformat()
                if self._long_extreme_time
                else None
            ),
            "long_level": int(self._long_level),
            "short_monitoring": self._short_monitoring,
            "short_extreme_value": self._short_extreme_value,
            "short_extreme_time": (
                self._short_extreme_time.isoformat()
                if self._short_extreme_time
                else None
            ),
            "short_level": int(self._short_level),
            "position_dir": self._position_dir,
            "entry_price": self._entry_price,
            "holding_periods": self._holding_periods,
            "max_profit": self._max_profit,
            "additional_positions_count": self._additional_positions_count,
            "last_kline_ts": self._last_kline_ts,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        self._mode = data.get("mode", "monitoring")
        self._cooling_count = int(data.get("cooling_count", 0))

        self._long_monitoring = bool(data.get("long_monitoring", False))
        self._long_extreme_value = data.get("long_extreme_value")
        long_t = data.get("long_extreme_time")
        self._long_extreme_time = datetime.fromisoformat(long_t) if long_t else None
        self._long_level = RsiLevel(int(data.get("long_level", 0)))

        self._short_monitoring = bool(data.get("short_monitoring", False))
        self._short_extreme_value = data.get("short_extreme_value")
        short_t = data.get("short_extreme_time")
        self._short_extreme_time = (
            datetime.fromisoformat(short_t) if short_t else None
        )
        self._short_level = RsiLevel(int(data.get("short_level", 0)))

        self._position_dir = data.get("position_dir")
        self._entry_price = data.get("entry_price")
        self._holding_periods = int(data.get("holding_periods", 0))
        self._max_profit = float(data.get("max_profit", 0.0))
        self._additional_positions_count = int(
            data.get("additional_positions_count", 0)
        )
        self._last_kline_ts = data.get("last_kline_ts")


# ── 工具函数 ───────────────────────────────────────────────

def _ts_to_dt(ts: int) -> datetime:
    """K 线时间戳转 datetime,自动识别秒/毫秒级"""
    if ts == 0:
        return datetime.now(timezone.utc)
    if ts > 10_000_000_000:  # 13 位以上视为毫秒
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    return datetime.fromtimestamp(ts, tz=timezone.utc)
