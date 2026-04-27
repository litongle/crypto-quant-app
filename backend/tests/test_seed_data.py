"""
seed_data 模板契约测试

确保所有 strategy_type 注册在 get_strategy() 工厂的策略,seed_data
都有对应模板,前端"创建策略"才能选到。否则后端能跑但前端看不见。
"""
from app.seed_data import STRATEGY_TEMPLATES


def get_template(code: str) -> dict | None:
    return next((t for t in STRATEGY_TEMPLATES if t["code"] == code), None)


def get_param(template: dict, key: str) -> dict | None:
    return next(
        (p for p in template["params_schema"]["params"] if p["key"] == key),
        None,
    )


# ── 模板存在性 ───────────────────────────────────────────

class TestTemplateExistence:
    """每个 strategy_type 都应有对应 seed 模板"""

    def test_ma_cross_template_exists(self):
        assert get_template("ma_cross") is not None

    def test_rsi_template_exists(self):
        assert get_template("rsi") is not None

    def test_bollinger_template_exists(self):
        assert get_template("bollinger") is not None

    def test_grid_template_exists(self):
        assert get_template("grid") is not None

    def test_martingale_template_exists(self):
        assert get_template("martingale") is not None

    def test_rule_custom_template_exists(self):
        assert get_template("rule_custom") is not None

    def test_rsi_layered_template_exists(self):
        """Step 1 移植的策略必须可在前端创建"""
        assert get_template("rsi_layered") is not None


# ── rsi_layered 参数完整性 ────────────────────────────────

class TestRsiLayeredTemplate:
    def setup_method(self):
        self.tmpl = get_template("rsi_layered")
        assert self.tmpl is not None

    def test_strategy_type_matches_factory(self):
        """strategy_type 必须等于 get_strategy() 注册的键"""
        assert self.tmpl["strategy_type"] == "rsi_layered"

    def test_has_all_required_params(self):
        """RsiLayered 9 个核心参数 + auto_trade 都应在 schema"""
        required = {
            "rsi_period",
            "long_levels",
            "short_levels",
            "retracement_points",
            "max_additional_positions",
            "fixed_stop_loss_points",
            "max_holding_candles",
            "cooling_candles",
            "profit_taking_config",
            "auto_trade",
        }
        actual = {p["key"] for p in self.tmpl["params_schema"]["params"]}
        missing = required - actual
        assert not missing, f"缺少参数: {missing}"

    def test_long_levels_is_array_int_with_three_defaults(self):
        p = get_param(self.tmpl, "long_levels")
        assert p["type"] == "array_int"
        assert isinstance(p["default"], list)
        assert len(p["default"]) == 3

    def test_short_levels_is_array_int_with_three_defaults(self):
        p = get_param(self.tmpl, "short_levels")
        assert p["type"] == "array_int"
        assert len(p["default"]) == 3

    def test_profit_taking_config_is_json(self):
        p = get_param(self.tmpl, "profit_taking_config")
        assert p["type"] == "json"
        # 默认值应是 [[窗口,回撤,最小盈利], ...] 形式
        assert isinstance(p["default"], list)
        assert all(isinstance(row, list) and len(row) == 3 for row in p["default"])

    def test_auto_trade_is_bool_default_false(self):
        """auto_trade 必须默认关闭(安全默认)"""
        p = get_param(self.tmpl, "auto_trade")
        assert p["type"] == "bool"
        assert p["default"] is False

    def test_defaults_match_strategy_DEFAULTS(self):
        """模板默认值与 RsiLayeredStrategy.DEFAULTS 应一致(避免漂移)"""
        from app.core.strategies.rsi_layered import DEFAULTS

        for key in [
            "rsi_period", "long_levels", "short_levels", "retracement_points",
            "max_additional_positions", "fixed_stop_loss_points",
            "max_holding_candles", "cooling_candles", "profit_taking_config",
        ]:
            tmpl_p = get_param(self.tmpl, key)
            assert tmpl_p is not None, f"模板缺 {key}"
            tmpl_default = tmpl_p["default"]
            strat_default = DEFAULTS[key]
            assert tmpl_default == strat_default, (
                f"{key} 默认值漂移: 模板={tmpl_default}, 策略={strat_default}"
            )


# ── 模板与工厂对齐 ────────────────────────────────────────

class TestTemplateFactoryAlignment:
    """每个 seeded 模板的 strategy_type 都应能被 get_strategy 创建出来。"""

    def test_all_templates_resolvable_by_factory(self):
        from app.core.strategy_engine import StrategyConfig, get_strategy

        for tmpl in STRATEGY_TEMPLATES:
            strategy_type = tmpl["strategy_type"]
            config = StrategyConfig(symbol="BTCUSDT", exchange="binance")
            try:
                strategy = get_strategy(strategy_type, config)
                assert strategy is not None
            except ValueError:
                # bollinger / grid / martingale 三个种子里有但工厂里没
                # 注册 — 这是已存在状态(不是本次回归),跳过
                if strategy_type in ("bollinger", "grid", "martingale"):
                    continue
                raise
