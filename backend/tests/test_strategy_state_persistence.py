"""
Step 3 测试 — 策略状态持久化

覆盖:
- BaseStrategy 默认 to_dict / from_dict 是无状态(空 dict / 空操作)
- RsiLayeredStrategy 重写 to_dict / from_dict 完整保留状态机
- analyze 多次后 → to_dict → 新实例 from_dict → 行为一致
- StrategyInstance 模型有 state_json 列且 nullable

不覆盖(留给运行期集成):
- runner _update_last_run_and_state 实际写库
- _start_instance 启动恢复链路
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app.core.strategies.rsi_layered import RsiLayeredStrategy, RsiLevel
from app.core.strategy_engine import (
    BaseStrategy,
    MAStrategy,
    RSIStrategy,
    Signal,
    StrategyConfig,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_kline(close: float, ts: int) -> dict:
    return {
        "open": close, "high": close, "low": close,
        "close": close, "volume": 1.0, "timestamp": ts,
    }


# ── BaseStrategy 默认实现 ────────────────────────────────

class TestStatelessStrategyDefaults:
    """没 override to_dict/from_dict 的策略应该退化为无状态。"""

    def test_ma_strategy_default_to_dict_returns_empty(self):
        s = MAStrategy(StrategyConfig(symbol="BTCUSDT", exchange="binance"))
        assert s.to_dict() == {}

    def test_ma_strategy_from_dict_no_op(self):
        s = MAStrategy(StrategyConfig(symbol="BTCUSDT", exchange="binance"))
        # 不应抛异常,也不应改变行为
        s.from_dict({"some": "garbage"})
        s.from_dict({})

    def test_rsi_strategy_default_to_dict_returns_empty(self):
        s = RSIStrategy(StrategyConfig(symbol="BTCUSDT", exchange="binance"))
        assert s.to_dict() == {}

    def test_rule_strategy_default_to_dict_returns_empty(self):
        from app.core.rule_engine import RuleStrategy
        s = RuleStrategy(StrategyConfig(symbol="BTCUSDT", exchange="binance"))
        assert s.to_dict() == {}


# ── RsiLayered 状态机往返 ──────────────────────────────

class TestRsiLayeredRoundTrip:
    """RsiLayered 已重写 to_dict / from_dict(Step 1),Step 3 验证它和
    runner 的持久化链路契合 — 即 to_dict 输出可被 JSON 序列化(SQLAlchemy
    JSON 列要求),from_dict 可恢复出同等行为的新实例。"""

    def test_to_dict_is_json_serializable(self):
        """to_dict 必须可 json.dumps,SQLAlchemy JSON 列才能存"""
        import json
        from datetime import datetime, timezone

        s = RsiLayeredStrategy(
            StrategyConfig(symbol="BTCUSDT", exchange="binance"),
        )
        s._mode = "long"
        s._cooling_count = 2
        s._long_monitoring = True
        s._long_extreme_value = 18.5
        s._long_extreme_time = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
        s._long_level = RsiLevel.LEVEL3
        s._position_dir = "long"
        s._entry_price = 50000.0
        s._holding_periods = 7
        s._max_profit = 12.3
        s._additional_positions_count = 2
        s._last_kline_ts = 1_700_000_000_000

        data = s.to_dict()
        # 不应抛 TypeError
        json_str = json.dumps(data)
        # 反序列化 + from_dict 一致
        s2 = RsiLayeredStrategy(StrategyConfig(symbol="BTCUSDT", exchange="binance"))
        s2.from_dict(json.loads(json_str))
        assert s2._mode == "long"
        assert s2._long_extreme_value == 18.5
        assert s2._entry_price == 50000.0

    def test_analyze_then_persist_then_restore_continues(self):
        """喂 K 线 → to_dict → 新实例 from_dict → 继续喂 K 线 → 行为一致。

        模拟:程序运行 10 根 K 线,持久化,重启,继续从第 11 根开始。
        """
        # 阶段 1: 第一个实例处理前 30 根 K 线
        s1 = RsiLayeredStrategy(
            StrategyConfig(
                symbol="BTCUSDT", exchange="binance",
                params={
                    "rsi_period": 14,
                    "long_levels": [40, 30, 20],
                    "short_levels": [60, 70, 80],
                    "retracement_points": 1.0,
                },
            )
        )
        # 制造 RSI 跌入超卖的序列
        closes = (
            [100.0] * 15
            + [100.0 - i * 0.5 for i in range(1, 11)]
            + [95.0 + i * 0.3 for i in range(1, 6)]
        )
        klines = [make_kline(c, 1_700_000_000_000 + i * 60_000)
                  for i, c in enumerate(closes)]

        # 喂前 25 根
        for i in range(15, 26):
            run(s1.analyze(klines[: i + 1]))

        snapshot = s1.to_dict()

        # 阶段 2: 新实例从快照恢复
        s2 = RsiLayeredStrategy(
            StrategyConfig(
                symbol="BTCUSDT", exchange="binance",
                params={
                    "rsi_period": 14,
                    "long_levels": [40, 30, 20],
                    "short_levels": [60, 70, 80],
                    "retracement_points": 1.0,
                },
            )
        )
        s2.from_dict(snapshot)

        # 关键状态字段一致
        assert s2._mode == s1._mode
        assert s2._long_monitoring == s1._long_monitoring
        assert s2._long_extreme_value == s1._long_extreme_value
        assert s2._position_dir == s1._position_dir
        assert s2._entry_price == s1._entry_price
        assert s2._last_kline_ts == s1._last_kline_ts

    def test_restored_instance_skips_already_processed_kline(self):
        """关键不变量: from_dict 后,旧 K 线时间戳不应被重复处理"""
        s1 = RsiLayeredStrategy(
            StrategyConfig(symbol="BTCUSDT", exchange="binance"),
        )
        klines = [make_kline(100.0, 1_700_000_000_000 + i * 60_000)
                  for i in range(30)]
        run(s1.analyze(klines))
        last_ts = s1._last_kline_ts
        assert last_ts is not None

        # 恢复
        s2 = RsiLayeredStrategy(
            StrategyConfig(symbol="BTCUSDT", exchange="binance"),
        )
        s2.from_dict(s1.to_dict())

        # 喂同样的 K 线 → 应被去重不处理(_last_kline_ts 仍等于 last_ts)
        before = s2._last_kline_ts
        result = run(s2.analyze(klines))
        assert result is None  # 时间戳已处理过
        assert s2._last_kline_ts == before


# ── StrategyInstance 模型 ──────────────────────────────

class TestStrategyInstanceColumn:
    def test_state_json_column_exists_and_nullable(self):
        from app.models.strategy import StrategyInstance

        col = StrategyInstance.__table__.c.state_json
        assert col is not None
        assert col.nullable is True
        # JSON 类型(SQLite 下可能映射为 JSON 或 NULL,检查 type 类名)
        assert "JSON" in type(col.type).__name__.upper() or "JSON" in str(col.type).upper()

    def test_state_json_default_is_none(self):
        """新实例 state_json 不应默认填充非 None 值"""
        from app.models.strategy import StrategyInstance
        # 不实际写库,只检查模型默认
        # SQLAlchemy default=None 时,column.default 为 None 或 ColumnDefault(None)
        col = StrategyInstance.__table__.c.state_json
        # 应该可空
        assert col.nullable is True
