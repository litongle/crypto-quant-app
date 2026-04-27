"""
RsiLayeredStrategy 单元测试

覆盖:
- 工厂注册
- RSI 计算前置条件
- 极值追踪与回撤检测
- 4 个状态机分支(monitoring / long / short / cooling)
- 加仓 / 分层止盈 / 固定止损 / 超时平仓 / 反手交易
- 方向过滤(direction=long/short/both)
- 状态序列化往返(to_dict / from_dict)
"""
import asyncio

import pytest

from app.core.strategies.rsi_layered import (
    DEFAULTS,
    RsiLayeredStrategy,
    RsiLevel,
)
from app.core.strategy_engine import Signal, StrategyConfig, get_strategy


# ── 测试辅助 ──────────────────────────────────────────────

def make_kline(close: float, ts: int) -> dict:
    """构造一根简化 K 线(timestamp 单位:毫秒)"""
    return {
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
        "timestamp": ts,
    }


def make_klines(closes: list[float], start_ts_ms: int = 1_700_000_000_000) -> list[dict]:
    """按 1 分钟间隔构造 K 线序列"""
    return [
        make_kline(c, start_ts_ms + i * 60_000) for i, c in enumerate(closes)
    ]


def run(coro):
    """同步运行协程的小工具"""
    return asyncio.run(coro)


def make_strategy(**param_overrides) -> RsiLayeredStrategy:
    """构造测试用策略实例(参数可覆盖)"""
    config = StrategyConfig(
        symbol="BTCUSDT",
        exchange="binance",
        direction="both",
        params=param_overrides,
    )
    return RsiLayeredStrategy(config)


# ── 工厂注册 ──────────────────────────────────────────────

class TestFactory:
    def test_factory_returns_rsi_layered(self):
        config = StrategyConfig(symbol="BTCUSDT", exchange="binance")
        s = get_strategy("rsi_layered", config)
        assert isinstance(s, RsiLayeredStrategy)
        assert s.strategy_type == "rsi_layered"


# ── analyze 前置条件 ──────────────────────────────────────

class TestAnalyzePreconditions:
    def test_returns_none_when_klines_too_few(self):
        s = make_strategy(rsi_period=14)
        # 14 根 K 线不够算 RSI(需要 period+1)
        klines = make_klines([100.0] * 14)
        assert run(s.analyze(klines)) is None

    def test_same_kline_ts_only_processed_once(self):
        s = make_strategy()
        klines = make_klines([100.0] * 30)
        run(s.analyze(klines))
        assert s._last_kline_ts == klines[-1]["timestamp"]
        # 再次喂同一序列(末尾 ts 相同)应直接返回 None,不更新状态
        rsi_before = s._long_extreme_value
        run(s.analyze(klines))
        assert s._long_extreme_value == rsi_before

    def test_returns_none_for_flat_prices(self):
        """全平价时 RSI 不会进入分层区,无信号"""
        s = make_strategy()
        klines = make_klines([100.0] * 30)
        sig = run(s.analyze(klines))
        assert sig is None
        assert s._mode == "monitoring"


# ── RSI 分层 ──────────────────────────────────────────────

class TestRsiLevel:
    def test_long_level_classification(self):
        s = make_strategy(long_levels=[30, 25, 20])
        assert s._check_rsi_level(35.0) == (RsiLevel.NONE, RsiLevel.NONE)
        assert s._check_rsi_level(30.0)[0] == RsiLevel.LEVEL1
        assert s._check_rsi_level(25.0)[0] == RsiLevel.LEVEL2
        assert s._check_rsi_level(20.0)[0] == RsiLevel.LEVEL3
        assert s._check_rsi_level(10.0)[0] == RsiLevel.LEVEL3

    def test_short_level_classification(self):
        s = make_strategy(short_levels=[70, 75, 80])
        assert s._check_rsi_level(65.0) == (RsiLevel.NONE, RsiLevel.NONE)
        assert s._check_rsi_level(70.0)[1] == RsiLevel.LEVEL1
        assert s._check_rsi_level(75.0)[1] == RsiLevel.LEVEL2
        assert s._check_rsi_level(80.0)[1] == RsiLevel.LEVEL3
        assert s._check_rsi_level(95.0)[1] == RsiLevel.LEVEL3


# ── 极值追踪与回撤 ────────────────────────────────────────

class TestExtremeTracking:
    def test_long_extreme_tracks_minimum(self):
        from datetime import datetime, timezone
        s = make_strategy()
        ts = datetime.now(timezone.utc)
        s._update_extreme_values(28.0, ts, RsiLevel.LEVEL1, RsiLevel.NONE)
        assert s._long_extreme_value == 28.0
        s._update_extreme_values(25.0, ts, RsiLevel.LEVEL2, RsiLevel.NONE)
        assert s._long_extreme_value == 25.0  # 更低,更新
        s._update_extreme_values(27.0, ts, RsiLevel.LEVEL1, RsiLevel.NONE)
        assert s._long_extreme_value == 25.0  # 不更新(更高)
        # level 应保留最深
        assert s._long_level == RsiLevel.LEVEL2

    def test_short_extreme_tracks_maximum(self):
        from datetime import datetime, timezone
        s = make_strategy()
        ts = datetime.now(timezone.utc)
        s._update_extreme_values(72.0, ts, RsiLevel.NONE, RsiLevel.LEVEL1)
        assert s._short_extreme_value == 72.0
        s._update_extreme_values(78.0, ts, RsiLevel.NONE, RsiLevel.LEVEL2)
        assert s._short_extreme_value == 78.0
        s._update_extreme_values(75.0, ts, RsiLevel.NONE, RsiLevel.LEVEL1)
        assert s._short_extreme_value == 78.0
        assert s._short_level == RsiLevel.LEVEL2

    def test_retracement_detection(self):
        s = make_strategy(retracement_points=2.0)
        s._long_monitoring = True
        s._long_extreme_value = 20.0
        long_sig, _ = s._check_retracement(21.5)  # 回撤 1.5,不够
        assert long_sig is False
        long_sig, _ = s._check_retracement(22.0)  # 回撤 2.0,达标
        assert long_sig is True


# ── 状态机:开仓 ────────────────────────────────────────────

class TestMonitoringMode:
    def test_long_open_signal_emitted(self):
        """构造一个 RSI 先跌至超卖、再回升触发回撤的序列"""
        s = make_strategy(
            rsi_period=14,
            long_levels=[40, 30, 20],   # 放宽阈值便于测试
            short_levels=[60, 70, 80],
            retracement_points=1.0,
        )
        # 先 15 根平价,再 10 根连跌(让 RSI 跌入超卖区),再 5 根连涨(触发回撤)
        closes = [100.0] * 15 + [100.0 - i * 0.5 for i in range(1, 11)] + [
            95.0 + i * 0.3 for i in range(1, 6)
        ]
        klines = make_klines(closes)
        # 喂全部 K 线,模拟 runner 每根都调用 analyze
        signals = []
        for i in range(15, len(klines)):
            sig = run(s.analyze(klines[: i + 1]))
            if sig is not None:
                signals.append(sig)
        # 应该至少有一根触发开多
        opens = [s for s in signals if s.metadata.get("intent") == "open"]
        assert len(opens) >= 1
        assert opens[0].action == "buy"
        assert opens[0].metadata["direction"] == "long"

    def test_direction_filter_blocks_long_when_short_only(self):
        s = make_strategy(retracement_points=1.0)
        s.config = StrategyConfig(
            symbol="BTCUSDT", exchange="binance", direction="short",
            params={"retracement_points": 1.0},
        )
        # 强制进入有多头回撤信号的状态
        s._long_monitoring = True
        s._long_extreme_value = 20.0
        kline = make_kline(100.0, 1_700_000_000_000)
        sig = s._on_monitoring(rsi=22.0, kline=kline)
        assert sig is None
        assert s._mode == "monitoring"  # 未开仓


# ── 状态机:持仓中行为 ────────────────────────────────────

class TestLongMode:
    def _setup_long_position(self, entry_price: float = 100.0) -> RsiLayeredStrategy:
        s = make_strategy(
            fixed_stop_loss_points=6.0,
            max_holding_candles=60,
            max_additional_positions=4,
        )
        kline = make_kline(entry_price, 1_700_000_000_000)
        s._open_position("long", kline)
        return s

    def test_stop_loss_triggers(self):
        s = self._setup_long_position(entry_price=100.0)
        # 价格跌 7 点 > 止损阈值 6
        kline = make_kline(93.0, 1_700_000_000_000 + 60_000)
        sig = s._on_long(rsi=50.0, kline=kline)
        assert sig is not None
        assert sig.action == "sell"
        assert sig.metadata["intent"] == "stop_loss"
        assert s._mode == "cooling"
        assert s._position_dir is None

    def test_take_profit_triggers_after_window_and_retracement(self):
        s = self._setup_long_position(entry_price=100.0)
        # 用第一档止盈: 窗口 10 根 / 回撤 3 / 最小盈利 2
        s._holding_periods = 10
        s._max_profit = 5.0
        # 当前盈利 = 102 - 100 = 2 → 回撤 = 5 - 2 = 3,达标且当前盈利 >= 2
        kline = make_kline(102.0, 1_700_000_000_000 + 60_000)
        sig = s._on_long(rsi=50.0, kline=kline)
        assert sig is not None
        assert sig.action == "sell"
        assert sig.metadata["intent"] == "take_profit"

    def test_take_profit_not_triggered_when_holding_too_short(self):
        s = self._setup_long_position(entry_price=100.0)
        s._holding_periods = 5  # 不到第一档窗口 10
        s._max_profit = 5.0
        kline = make_kline(102.0, 1_700_000_000_000 + 60_000)
        sig = s._on_long(rsi=50.0, kline=kline)
        # 此时只剩超时和加仓判断,都不应触发
        assert sig is None

    def test_add_position_triggers_on_long_retracement(self):
        s = self._setup_long_position(entry_price=100.0)
        # 制造一个多头回撤信号
        s._long_monitoring = True
        s._long_extreme_value = 20.0
        s._holding_periods = 5  # 没超时
        kline = make_kline(100.5, 1_700_000_000_000 + 60_000)  # PnL=0.5,不止损止盈
        sig = s._on_long(rsi=22.0, kline=kline)  # 回撤 2.0 ≥ 默认 2.0
        assert sig is not None
        assert sig.action == "buy"
        assert sig.metadata["intent"] == "add"
        assert s._additional_positions_count == 1
        assert s._mode == "long"  # 仍在持仓

    def test_add_position_capped_at_max(self):
        s = self._setup_long_position()
        s._additional_positions_count = 4  # 已达上限
        s._long_monitoring = True
        s._long_extreme_value = 20.0
        kline = make_kline(100.5, 1_700_000_000_000 + 60_000)
        sig = s._on_long(rsi=22.0, kline=kline)
        # 不应触发加仓(也不应触发其他)
        assert sig is None or sig.metadata.get("intent") != "add"

    def test_timeout_close(self):
        s = self._setup_long_position()
        s._holding_periods = 60  # 达到 max_holding_candles
        kline = make_kline(100.5, 1_700_000_000_000 + 60_000)
        sig = s._on_long(rsi=50.0, kline=kline)
        assert sig is not None
        assert sig.action == "sell"
        assert sig.metadata["intent"] == "timeout"
        assert s._mode == "cooling"

    def test_reverse_trade_when_timeout_and_short_signal(self):
        s = self._setup_long_position()
        s._holding_periods = 60  # 已超时
        s._short_monitoring = True
        s._short_extreme_value = 80.0
        kline = make_kline(100.5, 1_700_000_000_000 + 60_000)
        sig = s._on_long(rsi=78.0, kline=kline)  # 短信号回撤 2,达标
        assert sig is not None
        assert sig.action == "sell"
        assert sig.metadata["intent"] == "reverse"
        assert sig.metadata["direction"] == "short"
        assert s._position_dir == "short"


class TestShortMode:
    def _setup_short_position(self, entry_price: float = 100.0) -> RsiLayeredStrategy:
        s = make_strategy(fixed_stop_loss_points=6.0, max_holding_candles=60)
        kline = make_kline(entry_price, 1_700_000_000_000)
        s._open_position("short", kline)
        return s

    def test_short_stop_loss_when_price_rises(self):
        s = self._setup_short_position(100.0)
        # 空头止损:价格涨 7 点 → PnL = 100-107 = -7 ≤ -6
        kline = make_kline(107.0, 1_700_000_000_000 + 60_000)
        sig = s._on_short(rsi=50.0, kline=kline)
        assert sig is not None
        assert sig.action == "buy"  # 平空 = 买入
        assert sig.metadata["intent"] == "stop_loss"

    def test_short_take_profit_when_price_falls(self):
        s = self._setup_short_position(100.0)
        s._holding_periods = 10
        s._max_profit = 5.0
        # PnL = 100-98 = 2,回撤 = 5-2 = 3,达标
        kline = make_kline(98.0, 1_700_000_000_000 + 60_000)
        sig = s._on_short(rsi=50.0, kline=kline)
        assert sig is not None
        assert sig.action == "buy"
        assert sig.metadata["intent"] == "take_profit"


# ── 冷却模式 ──────────────────────────────────────────────

class TestCoolingMode:
    def test_cooling_increments_and_resets_to_monitoring(self):
        s = make_strategy(cooling_candles=3)
        s._mode = "cooling"
        s._cooling_count = 0
        for _ in range(3):
            s._on_cooling()
        assert s._mode == "monitoring"
        assert s._cooling_count == 0

    def test_cooling_does_not_emit_signal(self):
        s = make_strategy(cooling_candles=3)
        s._mode = "cooling"
        assert s._on_cooling() is None


# ── 状态序列化 ────────────────────────────────────────────

class TestStateSerialization:
    def test_to_dict_then_from_dict_roundtrip(self):
        from datetime import datetime, timezone
        s1 = make_strategy()
        # 制造一些非默认状态
        s1._mode = "long"
        s1._cooling_count = 2
        s1._long_monitoring = True
        s1._long_extreme_value = 18.5
        s1._long_extreme_time = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
        s1._long_level = RsiLevel.LEVEL3
        s1._position_dir = "long"
        s1._entry_price = 50000.0
        s1._holding_periods = 7
        s1._max_profit = 12.3
        s1._additional_positions_count = 2
        s1._last_kline_ts = 1_700_000_000_000

        snapshot = s1.to_dict()

        s2 = make_strategy()
        s2.from_dict(snapshot)

        assert s2._mode == "long"
        assert s2._cooling_count == 2
        assert s2._long_monitoring is True
        assert s2._long_extreme_value == 18.5
        assert s2._long_extreme_time == s1._long_extreme_time
        assert s2._long_level == RsiLevel.LEVEL3
        assert s2._position_dir == "long"
        assert s2._entry_price == 50000.0
        assert s2._holding_periods == 7
        assert s2._max_profit == 12.3
        assert s2._additional_positions_count == 2
        assert s2._last_kline_ts == 1_700_000_000_000

    def test_to_dict_handles_none_optional_fields(self):
        s = make_strategy()  # 全新初始状态
        d = s.to_dict()
        assert d["long_extreme_value"] is None
        assert d["long_extreme_time"] is None
        assert d["position_dir"] is None
        assert d["entry_price"] is None

    def test_from_dict_restores_clean_state_from_empty(self):
        s = make_strategy()
        s.from_dict({})
        assert s._mode == "monitoring"
        assert s._position_dir is None
        assert s._long_level == RsiLevel.NONE


# ── Signal 形态 ──────────────────────────────────────────

class TestSignalShape:
    def test_signal_carries_metadata_for_runner(self):
        s = make_strategy()
        kline = make_kline(100.0, 1_700_000_000_000)
        sig = s._make_signal(
            action="buy", kline=kline, intent="open",
            direction="long", reason="test",
        )
        assert isinstance(sig, Signal)
        assert sig.action == "buy"
        assert sig.metadata == {
            "intent": "open",
            "direction": "long",
            "strategy": "rsi_layered",
        }
        assert sig.entry_price is not None


# ── 默认参数 sanity ───────────────────────────────────────

class TestDefaults:
    def test_defaults_have_three_long_and_short_levels(self):
        assert len(DEFAULTS["long_levels"]) == 3
        assert len(DEFAULTS["short_levels"]) == 3

    def test_defaults_long_levels_descending(self):
        # 多头阈值越往下越超卖
        assert DEFAULTS["long_levels"] == sorted(DEFAULTS["long_levels"], reverse=True)

    def test_defaults_short_levels_ascending(self):
        assert DEFAULTS["short_levels"] == sorted(DEFAULTS["short_levels"])
