"""
规则引擎 — 解析 JSON 规则定义并执行交易信号判断

核心流程：
  K线数据 → Indicator计算 → Condition匹配 → Logic组合 → Signal生成

安全性：纯数据驱动，无 exec()/eval()，指标和算子均为白名单。
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import numpy as np

from app.core.indicators import (
    calc_atr,
    calc_bollinger,
    calc_cci,
    calc_dema,
    calc_ema,
    calc_macd,
    calc_obv,
    calc_price,
    calc_price_change_pct,
    calc_rsi,
    calc_sma,
    calc_stoch_d,
    calc_stoch_k,
    calc_volume_ma,
)
from app.core.strategy_engine import BaseStrategy, Signal, StrategyConfig

logger = logging.getLogger(__name__)


# ── 规则 DSL 白名单 ────────────────────────────────────────

# 单值型指标：返回一个数组，取 [-1] 与阈值比较
VALUE_INDICATORS = {
    "price",
    "rsi",
    "ma",
    "ema",
    "dema",
    "bollinger_upper",
    "bollinger_lower",
    "bollinger_pct",
    "volume",
    "volume_ma",
    "atr",
    "macd",
    "price_change_pct",
    "stoch_k",
    "stoch_d",
    "cci",
    "obv",
}

# 事件型指标：返回两个数组，判断交叉
EVENT_INDICATORS = {
    "ma_cross",
    "macd_cross",
}

ALL_INDICATORS = VALUE_INDICATORS | EVENT_INDICATORS

VALID_OPERATORS = {
    ">", ">=", "<", "<=", "==",
    "cross_up", "cross_down",
}

VALID_LOGIC = {"AND", "OR"}

# 每个指标的最大条件数（防止性能炸弹）
MAX_CONDITIONS_PER_GROUP = 10
MAX_NESTING_DEPTH = 3


# ── 规则校验 ──────────────────────────────────────────────

class RuleValidationError(ValueError):
    """规则校验失败"""
    pass


def validate_rules(rules: dict) -> list[str]:
    """校验规则 DSL 格式，返回错误列表（空=合法）"""
    errors: list[str] = []

    buy_rules = rules.get("buy_rules")
    sell_rules = rules.get("sell_rules")

    if not buy_rules and not sell_rules:
        errors.append("至少需要 buy_rules 或 sell_rules 之一")

    for label, rule_group in [("buy_rules", buy_rules), ("sell_rules", sell_rules)]:
        if rule_group is None:
            continue
        _validate_rule_group(rule_group, label, errors, depth=0)

    risk = rules.get("risk", {})
    if risk:
        sl = risk.get("stop_loss_percent")
        tp = risk.get("take_profit_percent")
        conf = risk.get("confidence_base")
        if sl is not None and (sl <= 0 or sl > 50):
            errors.append("risk.stop_loss_percent 应在 (0, 50] 范围内")
        if tp is not None and (tp <= 0 or tp > 100):
            errors.append("risk.take_profit_percent 应在 (0, 100] 范围内")
        if conf is not None and (conf < 0.1 or conf > 1.0):
            errors.append("risk.confidence_base 应在 [0.1, 1.0] 范围内")

    return errors


def _validate_rule_group(group: dict, path: str, errors: list[str], depth: int):
    """递归校验规则组"""
    if depth > MAX_NESTING_DEPTH:
        errors.append(f"{path}: 嵌套层数超过 {MAX_NESTING_DEPTH}")
        return

    logic = group.get("logic", "AND")
    if logic not in VALID_LOGIC:
        errors.append(f"{path}.logic: 不支持的逻辑类型 '{logic}'，可选 {VALID_LOGIC}")

    conditions = group.get("conditions", [])
    if not conditions:
        errors.append(f"{path}.conditions: 不能为空")
        return

    if len(conditions) > MAX_CONDITIONS_PER_GROUP:
        errors.append(f"{path}.conditions: 最多 {MAX_CONDITIONS_PER_GROUP} 个条件，当前 {len(conditions)}")

    for i, cond in enumerate(conditions):
        cond_path = f"{path}.conditions[{i}]"
        # 嵌套规则组
        if "logic" in cond and "conditions" in cond:
            _validate_rule_group(cond, cond_path, errors, depth + 1)
            continue

        # 普通条件
        indicator = cond.get("indicator")
        if indicator not in ALL_INDICATORS:
            errors.append(f"{cond_path}.indicator: 不支持的指标 '{indicator}'")
            continue

        operator = cond.get("operator")
        if operator not in VALID_OPERATORS:
            errors.append(f"{cond_path}.operator: 不支持的算子 '{operator}'")
            continue

        # 事件型指标只能用 cross_up/cross_down
        if indicator in EVENT_INDICATORS and operator not in ("cross_up", "cross_down"):
            errors.append(f"{cond_path}: 事件指标 '{indicator}' 只支持 cross_up/cross_down")
            continue

        # 单值型指标不能用 cross_up/cross_down
        if indicator in VALUE_INDICATORS and operator in ("cross_up", "cross_down"):
            errors.append(f"{cond_path}: 单值指标 '{indicator}' 不支持 {operator}")
            continue

        # 单值型必须有 value
        if indicator in VALUE_INDICATORS and operator not in ("cross_up", "cross_down"):
            if "value" not in cond and cond.get("value") != 0:
                errors.append(f"{cond_path}: 单值指标需要 value 字段")


# ── 规则引擎核心 ──────────────────────────────────────────

class RuleEngine:
    """规则引擎：根据 JSON 规则评估 K 线数据"""

    def __init__(self, klines: list[dict]):
        self.klines = klines
        self.closes = np.array([float(k["close"]) for k in klines], dtype=np.float64)
        self.highs = np.array(
            [float(k.get("high", k["close"])) for k in klines], dtype=np.float64
        )
        self.lows = np.array(
            [float(k.get("low", k["close"])) for k in klines], dtype=np.float64
        )
        self.volumes = np.array(
            [float(k.get("volume", 0)) for k in klines], dtype=np.float64
        )
        self._cache: dict[str, Any] = {}

    # ── 指标计算调度 ──

    def _calc_indicator(self, indicator: str, params: dict) -> Any:
        """根据指标名调度计算，返回 numpy 数组或数组元组"""
        dispatch = {
            "price": lambda: calc_price(self.closes),
            "rsi": lambda: calc_rsi(self.closes, params.get("period", 14)),
            "ma": lambda: calc_sma(self.closes, params.get("period", 20)),
            "ema": lambda: calc_ema(self.closes, params.get("period", 20)),
            "dema": lambda: calc_dema(self.closes, params.get("period", 20)),
            "bollinger_upper": lambda: calc_bollinger(
                self.closes, params.get("period", 20), params.get("std_dev", 2.0)
            )[0],
            "bollinger_lower": lambda: calc_bollinger(
                self.closes, params.get("period", 20), params.get("std_dev", 2.0)
            )[2],
            "bollinger_pct": lambda: calc_bollinger(
                self.closes, params.get("period", 20), params.get("std_dev", 2.0)
            )[3],
            "volume": lambda: self.volumes.copy(),
            "volume_ma": lambda: calc_volume_ma(self.volumes, params.get("period", 20)),
            "atr": lambda: calc_atr(
                self.highs, self.lows, self.closes, params.get("period", 14)
            ),
            "macd": lambda: calc_macd(
                self.closes,
                params.get("fast", 12),
                params.get("slow", 26),
                params.get("signal", 9),
            )[2],  # histogram
            "ma_cross": lambda: (
                calc_sma(self.closes, params.get("fast_period", 5)),
                calc_sma(self.closes, params.get("slow_period", 20)),
            ),
            "macd_cross": lambda: calc_macd(
                self.closes,
                params.get("fast", 12),
                params.get("slow", 26),
                params.get("signal", 9),
            )[:2],  # (macd_line, signal_line)
            "price_change_pct": lambda: calc_price_change_pct(
                self.closes, params.get("period", 1)
            ),
            "stoch_k": lambda: calc_stoch_k(
                self.highs, self.lows, self.closes, params.get("period", 14)
            ),
            "stoch_d": lambda: calc_stoch_d(
                self.highs,
                self.lows,
                self.closes,
                params.get("k_period", 14),
                params.get("d_period", 3),
            ),
            "cci": lambda: calc_cci(
                self.highs, self.lows, self.closes, params.get("period", 20)
            ),
            "obv": lambda: calc_obv(self.closes, self.volumes),
        }

        fn = dispatch.get(indicator)
        if fn is None:
            raise ValueError(f"不支持的指标: {indicator}")
        return fn()

    def _get_indicator_result(self, indicator: str, params: dict) -> Any:
        """获取指标计算结果（带缓存）"""
        cache_key = f"{indicator}:{sorted(params.items())}"
        if cache_key not in self._cache:
            self._cache[cache_key] = self._calc_indicator(indicator, params)
        return self._cache[cache_key]

    # ── 条件评估 ──

    def evaluate_condition(self, condition: dict) -> bool:
        """评估单个条件"""
        indicator = condition.get("indicator", "")
        params = condition.get("params", {})
        operator = condition.get("operator", "")
        value = condition.get("value")

        if indicator not in ALL_INDICATORS:
            logger.warning("未知指标: %s", indicator)
            return False

        if operator not in VALID_OPERATORS:
            logger.warning("未知算子: %s", operator)
            return False

        try:
            result = self._get_indicator_result(indicator, params)
        except Exception as e:
            logger.error("指标计算失败 %s(%s): %s", indicator, params, e)
            return False

        # 事件型指标
        if indicator in EVENT_INDICATORS:
            return self._evaluate_event(result, operator)

        # 单值型指标
        if isinstance(result, np.ndarray) and len(result) > 0:
            current = result[-1]
            if np.isnan(current):
                return False
            return self._compare(current, operator, value)

        return False

    def _evaluate_event(self, data: Any, operator: str) -> bool:
        """评估交叉事件（需要前一根和当前根比较）"""
        if not isinstance(data, tuple) or len(data) != 2:
            return False

        fast, slow = data
        if fast is None or slow is None:
            return False
        if len(fast) < 2 or len(slow) < 2:
            return False

        prev_diff = fast[-2] - slow[-2]
        curr_diff = fast[-1] - slow[-1]

        if np.isnan(prev_diff) or np.isnan(curr_diff):
            return False

        if operator == "cross_up":
            return prev_diff <= 0 and curr_diff > 0
        elif operator == "cross_down":
            return prev_diff >= 0 and curr_diff < 0

        return False

    @staticmethod
    def _compare(current: float, operator: str, value: float) -> bool:
        """数值比较"""
        comparators = {
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            "==": lambda a, b: abs(a - b) / (abs(b) + 1e-10) < 0.001,
        }
        fn = comparators.get(operator)
        if fn is None:
            return False
        try:
            return fn(float(current), float(value))
        except (TypeError, ValueError):
            return False

    # ── 规则组评估 ──

    def evaluate_rule_group(self, rule_group: dict) -> bool:
        """评估一组条件（含逻辑组合，支持嵌套）"""
        logic = rule_group.get("logic", "AND")
        conditions = rule_group.get("conditions", [])

        if not conditions:
            return False

        results = []
        for cond in conditions:
            # 嵌套规则组
            if "logic" in cond and "conditions" in cond:
                results.append(self.evaluate_rule_group(cond))
            else:
                results.append(self.evaluate_condition(cond))

        if logic == "AND":
            return all(results)
        elif logic == "OR":
            return any(results)

        return False


# ── RuleStrategy 策略类 ────────────────────────────────────

class RuleStrategy(BaseStrategy):
    """规则策略 — 根据 JSON 规则定义执行交易

    用法：
      strategy_type = "rule"
      params.rules = {
          "buy_rules": { "logic": "AND", "conditions": [...] },
          "sell_rules": { "logic": "OR", "conditions": [...] },
          "risk": { "stop_loss_percent": 3.0, "take_profit_percent": 6.0 }
      }
    """

    name = "自定义规则策略"
    strategy_type = "rule"

    async def analyze(self, klines: list[dict]) -> Signal | None:
        rules = self.config.params.get("rules") or self.config.params
        buy_rules = rules.get("buy_rules")
        sell_rules = rules.get("sell_rules")
        risk = rules.get("risk", {})

        if not buy_rules and not sell_rules:
            return None

        # 至少需要30根K线才能算大部分指标
        if len(klines) < 30:
            return None

        engine = RuleEngine(klines)
        current_price = Decimal(str(klines[-1]["close"]))

        sl_pct = Decimal(str(risk.get("stop_loss_percent", 3.0)))
        tp_pct = Decimal(str(risk.get("take_profit_percent", 6.0)))
        confidence = float(risk.get("confidence_base", 0.7))

        # 检查买入条件
        if buy_rules and self.config.direction in ("long", "both"):
            try:
                if engine.evaluate_rule_group(buy_rules):
                    return Signal(
                        action="buy",
                        confidence=confidence,
                        entry_price=current_price,
                        stop_loss_price=current_price * (1 - sl_pct / 100),
                        take_profit_price=current_price * (1 + tp_pct / 100),
                        reason=_build_reason(buy_rules, "买入"),
                        timestamp=datetime.now(timezone.utc),
                    )
            except Exception as e:
                logger.error("买入规则评估失败: %s", e)

        # 检查卖出条件
        if sell_rules and self.config.direction in ("short", "both"):
            try:
                if engine.evaluate_rule_group(sell_rules):
                    return Signal(
                        action="sell",
                        confidence=confidence,
                        entry_price=current_price,
                        stop_loss_price=current_price * (1 + sl_pct / 100),
                        take_profit_price=current_price * (1 - tp_pct / 100),
                        reason=_build_reason(sell_rules, "卖出"),
                        timestamp=datetime.now(timezone.utc),
                    )
            except Exception as e:
                logger.error("卖出规则评估失败: %s", e)

        return None


# ── 辅助函数 ──────────────────────────────────────────────

def _build_reason(rules: dict, prefix: str) -> str:
    """生成简短信号原因"""
    conditions = rules.get("conditions", [])
    parts = []
    for c in conditions:
        if "indicator" in c:
            ind = c["indicator"]
            op = c.get("operator", "?")
            val = c.get("value", "")
            if op in ("cross_up", "cross_down"):
                op_text = "上穿" if op == "cross_up" else "下穿"
                parts.append(f"{ind}{op_text}")
            else:
                parts.append(f"{ind} {op} {val}")
    return f"{prefix}: {' + '.join(parts)}" if parts else f"{prefix}: 规则触发"


def describe_rules(rules: dict) -> str:
    """生成人类可读的规则描述（用于 UI 展示）"""
    parts = []
    for key in ("buy_rules", "sell_rules"):
        group = rules.get(key)
        if not group:
            continue
        label = "买入" if key == "buy_rules" else "卖出"
        desc = _describe_rule_group(group)
        parts.append(f"{label}: {desc}")

    risk = rules.get("risk", {})
    if risk:
        sl = risk.get("stop_loss_percent", "?")
        tp = risk.get("take_profit_percent", "?")
        parts.append(f"止损{sl}%/止盈{tp}%")

    return " | ".join(parts)


def _describe_rule_group(group: dict) -> str:
    """递归描述规则组"""
    logic = group.get("logic", "AND")
    conditions = group.get("conditions", [])
    joiner = " 且 " if logic == "AND" else " 或 "

    parts = []
    for c in conditions:
        if "logic" in c and "conditions" in c:
            parts.append(f"({_describe_rule_group(c)})")
        elif "indicator" in c:
            ind = c["indicator"]
            op = c.get("operator", "?")
            val = c.get("value", "")
            params = c.get("params", {})
            params_str = ",".join(f"{k}={v}" for k, v in params.items()) if params else ""
            if op in ("cross_up", "cross_down"):
                op_text = "上穿" if op == "cross_up" else "下穿"
                parts.append(f"{ind}({params_str}) {op_text}" if params_str else f"{ind} {op_text}")
            else:
                parts.append(f"{ind}({params_str}) {op} {val}" if params_str else f"{ind} {op} {val}")

    return joiner.join(parts)
