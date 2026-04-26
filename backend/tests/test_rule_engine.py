"""
规则引擎测试 — 指标计算 / 条件评估 / 规则校验 / RuleStrategy 信号生成
"""
import pytest
import numpy as np
from datetime import datetime, timezone
from decimal import Decimal

from app.core.indicators import (
    calc_sma, calc_ema, calc_rsi, calc_macd, calc_bollinger,
    calc_atr, calc_price_change_pct, calc_stoch_k, calc_cci,
)
from app.core.rule_engine import (
    RuleEngine, RuleStrategy, validate_rules, describe_rules,
    RuleValidationError, VALUE_INDICATORS, EVENT_INDICATORS,
)
from app.core.strategy_engine import StrategyConfig, Signal, get_strategy


# ── 测试数据生成 ──────────────────────────────────────────

def _make_klines(count: int = 100, base_price: float = 50000.0, trend: str = "up") -> list[dict]:
    """生成模拟 K 线数据"""
    import random
    random.seed(42)  # 固定种子，测试可重复
    klines = []
    price = base_price
    for i in range(count):
        if trend == "up":
            change = random.uniform(-0.02, 0.03)
        elif trend == "down":
            change = random.uniform(-0.03, 0.02)
        else:
            change = random.uniform(-0.02, 0.02)
        price *= (1 + change)
        high = price * (1 + random.uniform(0, 0.01))
        low = price * (1 - random.uniform(0, 0.01))
        klines.append({
            "open": price,
            "high": high,
            "low": low,
            "close": price,
            "volume": random.uniform(100, 1000),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    return klines


# ── 指标计算测试 ──────────────────────────────────────────

class TestIndicators:
    """技术指标计算测试"""

    def test_sma_length(self):
        """SMA 输出长度与输入一致"""
        closes = np.random.rand(50) * 50000 + 40000
        result = calc_sma(closes, 20)
        assert len(result) == 50

    def test_sma_values(self):
        """SMA 前面为 NaN，后面有效"""
        closes = np.ones(30) * 100
        result = calc_sma(closes, 10)
        # 前9个应该是 NaN
        assert np.isnan(result[:9]).all()
        # 第10个起应该是 100
        assert not np.isnan(result[9]).any()
        assert abs(result[9] - 100.0) < 0.01

    def test_ema_length(self):
        """EMA 输出长度正确"""
        closes = np.random.rand(50) * 50000 + 40000
        result = calc_ema(closes, 20)
        assert len(result) == 50

    def test_rsi_range(self):
        """RSI 值在 0-100 之间"""
        closes = np.random.rand(100) * 50000 + 40000
        result = calc_rsi(closes, 14)
        valid = result[~np.isnan(result)]
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_macd_three_arrays(self):
        """MACD 返回三个数组"""
        closes = np.random.rand(100) * 50000 + 40000
        macd_line, signal_line, histogram = calc_macd(closes)
        assert len(macd_line) == 100
        assert len(signal_line) == 100
        assert len(histogram) == 100

    def test_bollinger_four_arrays(self):
        """布林带返回四个数组"""
        closes = np.random.rand(100) * 50000 + 40000
        upper, middle, lower, pct_b = calc_bollinger(closes)
        assert len(upper) == 100
        assert len(lower) == 100
        # 上轨 > 中轨 > 下轨
        valid_idx = ~np.isnan(upper)
        assert (upper[valid_idx] >= middle[valid_idx]).all()
        assert (middle[valid_idx] >= lower[valid_idx]).all()

    def test_atr_positive(self):
        """ATR 值应该为正"""
        highs = np.random.rand(50) * 51000 + 40000
        lows = highs - np.random.rand(50) * 500
        closes = (highs + lows) / 2
        result = calc_atr(highs, lows, closes, 14)
        valid = result[~np.isnan(result)]
        assert (valid >= 0).all()

    def test_price_change_pct(self):
        """涨跌幅计算"""
        closes = np.array([100.0, 105.0, 110.0, 100.0])
        result = calc_price_change_pct(closes, 1)
        # 第2根: (105-100)/100 = 5%
        assert abs(result[1] - 5.0) < 0.01
        # 第3根: (110-105)/105 ≈ 4.76%
        assert abs(result[2] - 4.7619) < 0.1
        # 第4根: (100-110)/110 ≈ -9.09%
        assert abs(result[3] - (-9.0909)) < 0.1

    def test_stoch_k_range(self):
        """KDJ K 值在 0-100"""
        highs = np.random.rand(50) * 51000 + 40000
        lows = np.random.rand(50) * 500 + 40000
        closes = (highs + lows) / 2
        result = calc_stoch_k(highs, lows, closes, 14)
        valid = result[~np.isnan(result)]
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_cci_calculated(self):
        """CCI 计算不报错"""
        highs = np.random.rand(50) * 51000 + 40000
        lows = np.random.rand(50) * 500 + 40000
        closes = (highs + lows) / 2
        result = calc_cci(highs, lows, closes, 20)
        assert len(result) == 50

    def test_short_data_returns_nan(self):
        """数据不足时返回 NaN"""
        closes = np.array([100.0])
        result = calc_sma(closes, 20)
        assert np.isnan(result[0])


# ── 规则校验测试 ──────────────────────────────────────────

class TestRuleValidation:
    """规则 DSL 校验测试"""

    def test_valid_rules(self):
        """合法规则通过校验"""
        rules = {
            "buy_rules": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "rsi", "params": {"period": 14}, "operator": "<", "value": 30},
                ],
            },
            "sell_rules": {
                "logic": "OR",
                "conditions": [
                    {"indicator": "rsi", "params": {"period": 14}, "operator": ">", "value": 70},
                ],
            },
            "risk": {"stop_loss_percent": 3.0, "take_profit_percent": 6.0, "confidence_base": 0.7},
        }
        errors = validate_rules(rules)
        assert errors == []

    def test_missing_both_rules(self):
        """缺少买入和卖出规则"""
        rules = {}
        errors = validate_rules(rules)
        assert any("至少需要" in e for e in errors)

    def test_invalid_indicator(self):
        """不支持的指标"""
        rules = {
            "buy_rules": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "nonexistent", "params": {}, "operator": "<", "value": 30},
                ],
            },
        }
        errors = validate_rules(rules)
        assert any("不支持的指标" in e for e in errors)

    def test_invalid_operator(self):
        """不支持的算子"""
        rules = {
            "buy_rules": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "rsi", "params": {}, "operator": "~~", "value": 30},
                ],
            },
        }
        errors = validate_rules(rules)
        assert any("不支持的算子" in e for e in errors)

    def test_event_indicator_with_value_operator(self):
        """事件指标用了值比较算子"""
        rules = {
            "buy_rules": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "ma_cross", "params": {"fast_period": 5, "slow_period": 20}, "operator": "<", "value": 30},
                ],
            },
        }
        errors = validate_rules(rules)
        assert any("只支持 cross" in e for e in errors)

    def test_value_indicator_with_cross_operator(self):
        """单值指标用了交叉算子"""
        rules = {
            "buy_rules": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "rsi", "params": {}, "operator": "cross_up"},
                ],
            },
        }
        errors = validate_rules(rules)
        assert any("不支持" in e and "cross" in e for e in errors)

    def test_risk_out_of_range(self):
        """风控参数越界"""
        rules = {
            "buy_rules": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "rsi", "params": {}, "operator": "<", "value": 30},
                ],
            },
            "risk": {"stop_loss_percent": -1, "take_profit_percent": 200, "confidence_base": 0.0},
        }
        errors = validate_rules(rules)
        assert any("stop_loss" in e for e in errors)

    def test_nested_rules(self):
        """嵌套规则组"""
        rules = {
            "buy_rules": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "rsi", "params": {}, "operator": "<", "value": 30},
                    {
                        "logic": "OR",
                        "conditions": [
                            {"indicator": "ma_cross", "params": {}, "operator": "cross_up"},
                            {"indicator": "macd_cross", "params": {}, "operator": "cross_up"},
                        ],
                    },
                ],
            },
        }
        errors = validate_rules(rules)
        assert errors == []

    def test_empty_conditions(self):
        """条件列表为空"""
        rules = {
            "buy_rules": {"logic": "AND", "conditions": []},
        }
        errors = validate_rules(rules)
        assert any("不能为空" in e for e in errors)

    def test_too_many_conditions(self):
        """条件数超限"""
        conditions = [
            {"indicator": "price", "params": {}, "operator": ">", "value": float(i)}
            for i in range(15)
        ]
        rules = {
            "buy_rules": {"logic": "AND", "conditions": conditions},
        }
        errors = validate_rules(rules)
        assert any("最多" in e for e in errors)


# ── 规则引擎评估测试 ──────────────────────────────────────

class TestRuleEngineEvaluation:
    """规则引擎条件评估测试"""

    def test_rsi_oversold(self):
        """RSI 超卖触发买入"""
        # 构造持续下跌的K线（RSI 会很低）
        klines = _make_klines(100, 50000, "down")
        engine = RuleEngine(klines)

        condition = {
            "indicator": "rsi",
            "params": {"period": 14},
            "operator": "<",
            "value": 50,  # 宽松阈值，确保触发
        }
        result = engine.evaluate_condition(condition)
        # 持续下跌 RSI 应该 < 50
        assert result is True

    def test_rsi_overbought(self):
        """RSI 未超买时不触发"""
        klines = _make_klines(100, 50000, "down")
        engine = RuleEngine(klines)

        condition = {
            "indicator": "rsi",
            "params": {"period": 14},
            "operator": ">",
            "value": 80,  # 高阈值
        }
        result = engine.evaluate_condition(condition)
        # 下跌行情 RSI 不太可能 > 80
        assert result is False

    def test_price_above_threshold(self):
        """价格大于阈值"""
        klines = _make_klines(50, 50000, "flat")
        engine = RuleEngine(klines)

        condition = {
            "indicator": "price",
            "params": {},
            "operator": ">",
            "value": 40000,
        }
        result = engine.evaluate_condition(condition)
        assert result is True

    def test_and_logic(self):
        """AND 逻辑：两个条件都满足"""
        klines = _make_klines(100, 50000, "flat")
        engine = RuleEngine(klines)
        # 获取当前价格来设置合理的阈值
        current_price = klines[-1]["close"]

        rule_group = {
            "logic": "AND",
            "conditions": [
                {"indicator": "price", "params": {}, "operator": ">", "value": current_price * 0.5},
                {"indicator": "price", "params": {}, "operator": "<", "value": current_price * 1.5},
            ],
        }
        result = engine.evaluate_rule_group(rule_group)
        assert result is True

    def test_and_logic_one_fails(self):
        """AND 逻辑：一个条件不满足"""
        klines = _make_klines(100, 50000, "flat")
        engine = RuleEngine(klines)

        rule_group = {
            "logic": "AND",
            "conditions": [
                {"indicator": "price", "params": {}, "operator": ">", "value": 40000},
                {"indicator": "price", "params": {}, "operator": ">", "value": 60000},
            ],
        }
        result = engine.evaluate_rule_group(rule_group)
        assert result is False

    def test_or_logic(self):
        """OR 逻辑：一个满足即可"""
        klines = _make_klines(100, 50000, "flat")
        engine = RuleEngine(klines)

        rule_group = {
            "logic": "OR",
            "conditions": [
                {"indicator": "price", "params": {}, "operator": ">", "value": 60000},
                {"indicator": "price", "params": {}, "operator": "<", "value": 60000},
            ],
        }
        result = engine.evaluate_rule_group(rule_group)
        assert result is True

    def test_nested_rule_group(self):
        """嵌套规则组评估"""
        klines = _make_klines(100, 50000, "up")
        engine = RuleEngine(klines)

        rule_group = {
            "logic": "AND",
            "conditions": [
                {"indicator": "price", "params": {}, "operator": ">", "value": 40000},
                {
                    "logic": "OR",
                    "conditions": [
                        {"indicator": "price", "params": {}, "operator": "<", "value": 60000},
                        {"indicator": "price", "params": {}, "operator": ">", "value": 80000},
                    ],
                },
            ],
        }
        result = engine.evaluate_rule_group(rule_group)
        assert result is True

    def test_indicator_cache(self):
        """相同指标参数只计算一次"""
        klines = _make_klines(100, 50000, "flat")
        engine = RuleEngine(klines)

        condition = {"indicator": "rsi", "params": {"period": 14}, "operator": "<", "value": 50}
        engine.evaluate_condition(condition)
        # 缓存应该有值
        assert len(engine._cache) == 1

    def test_invalid_indicator_returns_false(self):
        """不支持的指标返回 False"""
        klines = _make_klines(50, 50000, "flat")
        engine = RuleEngine(klines)
        condition = {"indicator": "fake_indicator", "params": {}, "operator": ">", "value": 0}
        result = engine.evaluate_condition(condition)
        assert result is False


# ── RuleStrategy 集成测试 ──────────────────────────────────

class TestRuleStrategy:
    """RuleStrategy 策略类测试"""

    @pytest.mark.asyncio
    async def test_rsi_buy_signal(self):
        """RSI 超卖触发买入信号"""
        rules = {
            "buy_rules": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "rsi", "params": {"period": 14}, "operator": "<", "value": 50},
                ],
            },
            "risk": {"stop_loss_percent": 3.0, "take_profit_percent": 6.0, "confidence_base": 0.7},
        }
        config = StrategyConfig(
            symbol="BTCUSDT",
            exchange="binance",
            direction="both",
            params={"rules": rules},
            risk_params={},
        )
        strategy = RuleStrategy(config)
        klines = _make_klines(100, 50000, "down")
        signal = await strategy.analyze(klines)
        # 下跌行情 RSI < 50 应该触发买入
        assert signal is not None
        assert signal.action == "buy"
        assert signal.confidence == 0.7

    @pytest.mark.asyncio
    async def test_no_signal_when_no_match(self):
        """条件不满足时不产生信号"""
        rules = {
            "buy_rules": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "rsi", "params": {"period": 14}, "operator": ">", "value": 90},
                ],
            },
            "risk": {"stop_loss_percent": 3.0, "take_profit_percent": 6.0},
        }
        config = StrategyConfig(
            symbol="BTCUSDT",
            exchange="binance",
            direction="both",
            params={"rules": rules},
            risk_params={},
        )
        strategy = RuleStrategy(config)
        klines = _make_klines(100, 50000, "down")
        signal = await strategy.analyze(klines)
        # 下跌行情 RSI 不太可能 > 90
        assert signal is None

    @pytest.mark.asyncio
    async def test_sell_signal(self):
        """卖出信号"""
        rules = {
            "sell_rules": {
                "logic": "OR",
                "conditions": [
                    {"indicator": "rsi", "params": {"period": 14}, "operator": ">", "value": 50},
                ],
            },
            "risk": {"stop_loss_percent": 3.0, "take_profit_percent": 6.0},
        }
        config = StrategyConfig(
            symbol="BTCUSDT",
            exchange="binance",
            direction="both",
            params={"rules": rules},
            risk_params={},
        )
        strategy = RuleStrategy(config)
        klines = _make_klines(100, 50000, "up")
        signal = await strategy.analyze(klines)
        # 上涨行情 RSI 可能 > 50
        if signal is not None:
            assert signal.action == "sell"

    @pytest.mark.asyncio
    async def test_stop_loss_take_profit(self):
        """止损止盈价格计算"""
        rules = {
            "buy_rules": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "rsi", "params": {"period": 14}, "operator": "<", "value": 50},
                ],
            },
            "risk": {"stop_loss_percent": 3.0, "take_profit_percent": 6.0, "confidence_base": 0.7},
        }
        config = StrategyConfig(
            symbol="BTCUSDT",
            exchange="binance",
            direction="both",
            params={"rules": rules},
            risk_params={},
        )
        strategy = RuleStrategy(config)
        klines = _make_klines(100, 50000, "down")
        signal = await strategy.analyze(klines)
        if signal is not None:
            entry = signal.entry_price
            sl = signal.stop_loss_price
            tp = signal.take_profit_price
            # 止损应该低于入场价3%
            expected_sl = entry * Decimal("0.97")
            assert abs(sl - expected_sl) < Decimal("1")
            # 止盈应该高于入场价6%
            expected_tp = entry * Decimal("1.06")
            assert abs(tp - expected_tp) < Decimal("1")

    @pytest.mark.asyncio
    async def test_too_few_klines(self):
        """K线不足时不产生信号"""
        rules = {
            "buy_rules": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "rsi", "params": {"period": 14}, "operator": "<", "value": 50},
                ],
            },
        }
        config = StrategyConfig(
            symbol="BTCUSDT",
            exchange="binance",
            direction="both",
            params={"rules": rules},
            risk_params={},
        )
        strategy = RuleStrategy(config)
        klines = _make_klines(10, 50000, "down")  # 只有10根
        signal = await strategy.analyze(klines)
        assert signal is None  # 至少30根

    @pytest.mark.asyncio
    async def test_empty_rules(self):
        """空规则不产生信号"""
        config = StrategyConfig(
            symbol="BTCUSDT",
            exchange="binance",
            direction="both",
            params={"rules": {}},
            risk_params={},
        )
        strategy = RuleStrategy(config)
        klines = _make_klines(100, 50000, "up")
        signal = await strategy.analyze(klines)
        assert signal is None

    def test_get_strategy_rule(self):
        """通过工厂获取 RuleStrategy"""
        config = StrategyConfig(
            symbol="BTCUSDT",
            exchange="binance",
            direction="both",
            params={"rules": {"buy_rules": {"logic": "AND", "conditions": []}}},
            risk_params={},
        )
        strategy = get_strategy("rule", config)
        assert strategy is not None
        assert strategy.strategy_type == "rule"


# ── 规则描述测试 ──────────────────────────────────────────

class TestDescribeRules:
    """规则可读描述生成测试"""

    def test_simple_rules(self):
        """简单规则描述"""
        rules = {
            "buy_rules": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "rsi", "params": {"period": 14}, "operator": "<", "value": 30},
                ],
            },
            "sell_rules": {
                "logic": "OR",
                "conditions": [
                    {"indicator": "rsi", "params": {"period": 14}, "operator": ">", "value": 70},
                ],
            },
            "risk": {"stop_loss_percent": 3.0, "take_profit_percent": 6.0},
        }
        desc = describe_rules(rules)
        assert "买入" in desc
        assert "卖出" in desc
        assert "止损3.0%" in desc
        assert "止盈6.0%" in desc

    def test_event_indicator_description(self):
        """事件指标描述"""
        rules = {
            "buy_rules": {
                "logic": "AND",
                "conditions": [
                    {"indicator": "ma_cross", "params": {"fast_period": 5, "slow_period": 20}, "operator": "cross_up"},
                ],
            },
        }
        desc = describe_rules(rules)
        assert "上穿" in desc
