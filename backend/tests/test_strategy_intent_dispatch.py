"""
Step 2a/2b 测试 — _auto_trade 的 intent 路由

覆盖:
- select_position_to_close 纯函数(Step 2a)
  - 空列表返回 None
  - 优先选本 instance 开的仓
  - direction 过滤 + 找不到时回退
  - 多个候选时取第一个
- 常量 CLOSE_INTENTS 形态(Step 2a)
- RsiLayered intent 契约(Step 2a/2b)
  - take_profit/stop_loss/timeout 路由到 close
  - reverse 不在 CLOSE_INTENTS(单独分支)
  - add 不在 CLOSE_INTENTS(走开仓路径)

不覆盖(留给后续集成测试):
- 实际 DB 查询和 OrderService.close_position 调用 — 需要完整
  fixture 链(User/Account/Position/Strategy + 交易所 mock)
"""
from dataclasses import dataclass

import pytest

from app.core.strategy_runner import (
    CLOSE_INTENTS,
    select_position_to_close,
)


@dataclass
class FakePosition:
    """简化 Position,只含 select_position_to_close 关心的字段"""
    id: int
    strategy_instance_id: int | None
    side: str  # "long" / "short"


# ── 常量形态 ──────────────────────────────────────────────

class TestIntentConstants:
    def test_close_intents_set_membership(self):
        assert "take_profit" in CLOSE_INTENTS
        assert "stop_loss" in CLOSE_INTENTS
        assert "timeout" in CLOSE_INTENTS
        assert "open" not in CLOSE_INTENTS
        assert "add" not in CLOSE_INTENTS
        assert "reverse" not in CLOSE_INTENTS  # reverse 单独分支处理


# ── 纯函数选位逻辑 ────────────────────────────────────────

class TestSelectPositionToClose:
    def test_empty_returns_none(self):
        assert select_position_to_close([], instance_id=1, direction=None) is None

    def test_single_position_returned(self):
        p = FakePosition(id=10, strategy_instance_id=1, side="long")
        assert select_position_to_close([p], instance_id=1, direction=None) is p

    def test_prefers_same_instance(self):
        # DB 里有 2 个仓: 一个是别的策略的,一个是本策略的
        other = FakePosition(id=10, strategy_instance_id=99, side="long")
        own = FakePosition(id=11, strategy_instance_id=7, side="long")
        result = select_position_to_close([other, own], instance_id=7, direction=None)
        assert result is own

    def test_falls_back_to_any_when_no_same_instance(self):
        # 都不是本策略开的(可能是手工开的) → 仍然能选(回退到任意一个)
        p1 = FakePosition(id=10, strategy_instance_id=99, side="long")
        p2 = FakePosition(id=11, strategy_instance_id=88, side="long")
        result = select_position_to_close([p1, p2], instance_id=7, direction=None)
        assert result in (p1, p2)

    def test_direction_filter_long(self):
        long_pos = FakePosition(id=10, strategy_instance_id=7, side="long")
        short_pos = FakePosition(id=11, strategy_instance_id=7, side="short")
        result = select_position_to_close(
            [long_pos, short_pos], instance_id=7, direction="long",
        )
        assert result is long_pos

    def test_direction_filter_short(self):
        long_pos = FakePosition(id=10, strategy_instance_id=7, side="long")
        short_pos = FakePosition(id=11, strategy_instance_id=7, side="short")
        result = select_position_to_close(
            [long_pos, short_pos], instance_id=7, direction="short",
        )
        assert result is short_pos

    def test_direction_filter_falls_back_when_no_match(self):
        """direction=long 但只有 short 仓 → 不应丢失目标,回退到原候选"""
        only_short = FakePosition(id=10, strategy_instance_id=7, side="short")
        result = select_position_to_close(
            [only_short], instance_id=7, direction="long",
        )
        assert result is only_short  # 回退,不返回 None

    def test_direction_none_does_not_filter(self):
        long_pos = FakePosition(id=10, strategy_instance_id=7, side="long")
        short_pos = FakePosition(id=11, strategy_instance_id=7, side="short")
        # direction=None: 不过滤,取第一个
        result = select_position_to_close(
            [long_pos, short_pos], instance_id=7, direction=None,
        )
        assert result is long_pos

    def test_direction_unknown_value_does_not_filter(self):
        """非 long/short 的 direction 值(防御性)→ 不过滤"""
        long_pos = FakePosition(id=10, strategy_instance_id=7, side="long")
        short_pos = FakePosition(id=11, strategy_instance_id=7, side="short")
        result = select_position_to_close(
            [long_pos, short_pos], instance_id=7, direction="weird",
        )
        assert result is long_pos  # 取第一个

    def test_combined_instance_and_direction(self):
        """本实例的 long + 别的实例的 short → 选本实例的 long"""
        own_long = FakePosition(id=10, strategy_instance_id=7, side="long")
        other_short = FakePosition(id=11, strategy_instance_id=99, side="short")
        result = select_position_to_close(
            [own_long, other_short], instance_id=7, direction="long",
        )
        assert result is own_long

    def test_instance_filter_takes_priority_over_direction(self):
        """本实例只有 short,别的实例有 long → 应选本实例 short(优先级:实例 > 方向)"""
        own_short = FakePosition(id=10, strategy_instance_id=7, side="short")
        other_long = FakePosition(id=11, strategy_instance_id=99, side="long")
        result = select_position_to_close(
            [own_short, other_long], instance_id=7, direction="long",
        )
        # 本实例只有 short,direction filter 后空 → 回退到本实例的 short
        assert result is own_short


# ── RsiLayered 信号 metadata 端到端契约 ─────────────────────

class TestRsiLayeredSignalContract:
    """验证 RsiLayered 发出的 metadata.intent 与 runner 路由集合对齐。

    这是一个跨模块"契约测试":如果有人改了 RsiLayered 的 intent 名字或
    runner 的 CLOSE_INTENTS 集合,这里会立刻报错。
    """

    def test_take_profit_routes_to_close(self):
        from app.core.strategies.rsi_layered import RsiLayeredStrategy
        from app.core.strategy_engine import StrategyConfig

        s = RsiLayeredStrategy(StrategyConfig(symbol="BTCUSDT", exchange="binance"))
        kline = {"close": 100.0, "timestamp": 1_700_000_000_000}
        s._open_position("long", kline)
        sig = s._close_signal_for("long", kline, "take_profit", "test")
        assert sig.metadata["intent"] == "take_profit"
        assert sig.metadata["intent"] in CLOSE_INTENTS

    def test_stop_loss_routes_to_close(self):
        from app.core.strategies.rsi_layered import RsiLayeredStrategy
        from app.core.strategy_engine import StrategyConfig

        s = RsiLayeredStrategy(StrategyConfig(symbol="BTCUSDT", exchange="binance"))
        kline = {"close": 100.0, "timestamp": 1_700_000_000_000}
        s._open_position("long", kline)
        sig = s._close_signal_for("long", kline, "stop_loss", "test")
        assert sig.metadata["intent"] in CLOSE_INTENTS

    def test_timeout_routes_to_close(self):
        from app.core.strategies.rsi_layered import RsiLayeredStrategy
        from app.core.strategy_engine import StrategyConfig

        s = RsiLayeredStrategy(StrategyConfig(symbol="BTCUSDT", exchange="binance"))
        kline = {"close": 100.0, "timestamp": 1_700_000_000_000}
        s._open_position("long", kline)
        sig = s._close_signal_for("long", kline, "timeout", "test")
        assert sig.metadata["intent"] in CLOSE_INTENTS

    def test_open_does_not_route_to_close(self):
        from app.core.strategies.rsi_layered import RsiLayeredStrategy
        from app.core.strategy_engine import StrategyConfig

        s = RsiLayeredStrategy(StrategyConfig(symbol="BTCUSDT", exchange="binance"))
        kline = {"close": 100.0, "timestamp": 1_700_000_000_000}
        sig = s._make_signal(
            action="buy", kline=kline, intent="open",
            direction="long", reason="test",
        )
        assert sig.metadata["intent"] not in CLOSE_INTENTS

    def test_reverse_intent_not_in_close_intents(self):
        """reverse 走单独 _auto_reverse_position 分支,不应被 CLOSE_INTENTS 截走"""
        from app.core.strategies.rsi_layered import RsiLayeredStrategy
        from app.core.strategy_engine import StrategyConfig

        s = RsiLayeredStrategy(StrategyConfig(symbol="BTCUSDT", exchange="binance"))
        kline = {"close": 100.0, "timestamp": 1_700_000_000_000}
        sig = s._make_signal(
            action="sell", kline=kline, intent="reverse",
            direction="short", reason="test",
        )
        assert sig.metadata["intent"] == "reverse"
        assert sig.metadata["intent"] not in CLOSE_INTENTS

    def test_add_intent_not_in_close_intents(self):
        """add 走开仓路径,不在 CLOSE_INTENTS 内"""
        from app.core.strategies.rsi_layered import RsiLayeredStrategy
        from app.core.strategy_engine import StrategyConfig

        s = RsiLayeredStrategy(StrategyConfig(symbol="BTCUSDT", exchange="binance"))
        kline = {"close": 100.0, "timestamp": 1_700_000_000_000}
        sig = s._make_signal(
            action="buy", kline=kline, intent="add",
            direction="long", reason="test",
        )
        assert sig.metadata["intent"] == "add"
        assert sig.metadata["intent"] not in CLOSE_INTENTS

    def test_reverse_metadata_direction_is_target(self):
        """RsiLayered 的反手信号: metadata.direction 是反手后的目标方向"""
        from app.core.strategies.rsi_layered import RsiLayeredStrategy
        from app.core.strategy_engine import StrategyConfig

        s = RsiLayeredStrategy(StrategyConfig(symbol="BTCUSDT", exchange="binance"))
        kline_open = {"close": 100.0, "timestamp": 1_700_000_000_000}
        # 先开多仓
        s._open_position("long", kline_open)
        s._holding_periods = 60  # 触发超时反手条件
        s._short_monitoring = True
        s._short_extreme_value = 80.0

        # 模拟反手到空
        kline = {"close": 100.0, "timestamp": 1_700_000_000_001}
        sig = s._on_long(rsi=78.0, kline=kline)  # 短信号回撤 2,触发反手

        assert sig is not None
        assert sig.metadata["intent"] == "reverse"
        # direction 是目标方向(short),不是被平方向
        assert sig.metadata["direction"] == "short"
        # action 与目标方向匹配:开空 = sell
        assert sig.action == "sell"
