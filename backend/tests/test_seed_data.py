"""
seed_data 模板契约测试

确保所有 strategy_type 注册在 get_strategy() 工厂的策略,seed_data
都有对应模板,前端"创建策略"才能选到。否则后端能跑但前端看不见。

含 upsert 行为测试(in-memory SQLite,不依赖外部 DB)。
"""

import asyncio

from app.seed_data import STRATEGY_TEMPLATES, upsert_strategy_templates


def get_template(code: str) -> dict | None:
    return next((t for t in STRATEGY_TEMPLATES if t["code"] == code), None)


def get_param(template: dict, key: str) -> dict | None:
    return next(
        (p for p in template["params_schema"]["params"] if p["key"] == key),
        None,
    )


LIVE_TRADING_TEMPLATE_CODES = {
    "ma_cross",
    "rsi",
    "bollinger",
    "grid",
    "martingale",
    "rule_custom",
    "rsi_layered",
    "dca",
}


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

    def test_dca_template_exists(self):
        assert get_template("dca") is not None


# ── rsi_layered 参数完整性 ────────────────────────────────


class TestRsiLayeredTemplate:
    def setup_method(self):
        self.tmpl = get_template("rsi_layered")
        assert self.tmpl is not None

    def test_strategy_type_matches_factory(self):
        """strategy_type 必须等于 get_strategy() 注册的键"""
        assert self.tmpl["strategy_type"] == "rsi_layered"

    def test_has_all_required_params(self):
        """核心参数 + 双模式头寸量纲 + auto_trade 都应在 schema"""
        required = {
            "rsi_period",
            "long_levels",
            "short_levels",
            "retracement_points",
            "max_additional_positions",
            "size_mode",
            "fixed_stop_loss_pct",
            "profit_taking_config_pct",
            "atr_period",
            "fixed_stop_loss_atr",
            "profit_taking_config_atr",
            "max_holding_candles",
            "cooling_candles",
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

    def test_profit_taking_config_pct_is_json_table(self):
        p = get_param(self.tmpl, "profit_taking_config_pct")
        assert p["type"] == "json_table"
        # 默认值应是 [[窗口,回撤百分比,最小盈利百分比], ...] 形式
        assert isinstance(p["default"], list)
        assert all(isinstance(row, list) and len(row) == 3 for row in p["default"])
        # columns 元数据描述每列含义
        assert isinstance(p.get("columns"), list)
        assert len(p["columns"]) == 3

    def test_profit_taking_config_atr_is_json_table(self):
        p = get_param(self.tmpl, "profit_taking_config_atr")
        assert p["type"] == "json_table"
        assert isinstance(p["default"], list)
        assert all(isinstance(row, list) and len(row) == 3 for row in p["default"])
        assert isinstance(p.get("columns"), list)
        assert len(p["columns"]) == 3

    def test_auto_trade_is_bool_default_false(self):
        """auto_trade 必须默认关闭(安全默认)"""
        p = get_param(self.tmpl, "auto_trade")
        assert p["type"] == "bool"
        assert p["default"] is False

    def test_defaults_match_strategy_defaults(self):
        """模板默认值与 RsiLayeredStrategy.DEFAULTS 应一致(避免漂移)"""
        from app.core.strategies.rsi_layered import DEFAULTS

        for key in [
            "rsi_period",
            "long_levels",
            "short_levels",
            "retracement_points",
            "max_additional_positions",
            "size_mode",
            "fixed_stop_loss_pct",
            "profit_taking_config_pct",
            "atr_period",
            "fixed_stop_loss_atr",
            "profit_taking_config_atr",
            "max_holding_candles",
            "cooling_candles",
        ]:
            tmpl_p = get_param(self.tmpl, key)
            assert tmpl_p is not None, f"模板缺 {key}"
            tmpl_default = tmpl_p["default"]
            strat_default = DEFAULTS[key]
            assert (
                tmpl_default == strat_default
            ), f"{key} 默认值漂移: 模板={tmpl_default}, 策略={strat_default}"


# ── 模板与工厂对齐 ────────────────────────────────────────


class TestTemplateFactoryAlignment:
    """每个 seeded 模板的 strategy_type 都应能被 get_strategy 创建出来。"""

    def test_all_templates_resolvable_by_factory(self):
        from app.core.strategy_engine import StrategyConfig, get_strategy

        for tmpl in STRATEGY_TEMPLATES:
            strategy_type = tmpl["strategy_type"]
            config = StrategyConfig(symbol="BTCUSDT", exchange="binance")
            strategy = get_strategy(strategy_type, config)
            assert strategy is not None


class TestLiveTradingTemplateParams:
    def test_supported_templates_expose_auto_trade(self):
        for code in LIVE_TRADING_TEMPLATE_CODES:
            template = get_template(code)
            assert template is not None, f"模板缺失: {code}"
            auto_trade = get_param(template, "auto_trade")
            assert auto_trade is not None, f"{code} 缺少 auto_trade"
            assert auto_trade["type"] == "bool"
            assert auto_trade["default"] is False

    def test_multi_symbol_does_not_expose_auto_trade(self):
        template = get_template("multi_symbol")
        assert template is not None
        assert get_param(template, "auto_trade") is None


# ── upsert 行为测试 ──────────────────────────────────────


async def _build_in_memory_session():
    """构造一个隔离的 in-memory SQLite session_maker(每个测试独立)。"""
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    import app.models  # noqa: F401 — 注册所有模型
    from app.database import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


class TestUpsertBehavior:
    def test_upsert_into_empty_db_inserts_all(self):
        """空表 → upsert → 所有模板插入,updated=0"""

        async def go():
            engine, session_factory = await _build_in_memory_session()
            try:
                async with session_factory() as s:
                    inserted, updated = await upsert_strategy_templates(s)
                    await s.commit()
                async with session_factory() as s:
                    from sqlalchemy import select

                    from app.models.strategy import StrategyTemplate

                    rows = (await s.execute(select(StrategyTemplate))).scalars().all()
                return inserted, updated, [r.code for r in rows]
            finally:
                await engine.dispose()

        inserted, updated, codes = asyncio.run(go())
        assert inserted == len(STRATEGY_TEMPLATES)
        assert updated == 0
        assert "rsi_layered" in codes
        assert len(codes) == len(STRATEGY_TEMPLATES)

    def test_upsert_idempotent(self):
        """连续两次 upsert,第二次应该全部跳过(0 新增 0 更新)"""

        async def go():
            engine, session_factory = await _build_in_memory_session()
            try:
                async with session_factory() as s:
                    await upsert_strategy_templates(s)
                    await s.commit()
                async with session_factory() as s:
                    inserted2, updated2 = await upsert_strategy_templates(s)
                    await s.commit()
                return inserted2, updated2
            finally:
                await engine.dispose()

        inserted2, updated2 = asyncio.run(go())
        assert inserted2 == 0
        assert updated2 == 0  # 数据无变化,不应记为 updated

    def test_upsert_updates_changed_fields(self):
        """已有模板字段被外部改过 → upsert 应改回最新值"""

        async def go():
            engine, session_factory = await _build_in_memory_session()
            try:
                # 先 seed 一次
                async with session_factory() as s:
                    await upsert_strategy_templates(s)
                    await s.commit()
                # 篡改 rsi_layered 模板的 name
                async with session_factory() as s:
                    from sqlalchemy import select

                    from app.models.strategy import StrategyTemplate

                    t = (
                        await s.execute(
                            select(StrategyTemplate).where(StrategyTemplate.code == "rsi_layered")
                        )
                    ).scalar_one()
                    t.name = "被改坏的名字"
                    t.is_active = False
                    await s.commit()
                # 再 upsert,应该恢复
                async with session_factory() as s:
                    inserted, updated = await upsert_strategy_templates(s)
                    await s.commit()
                async with session_factory() as s:
                    from sqlalchemy import select

                    from app.models.strategy import StrategyTemplate

                    t = (
                        await s.execute(
                            select(StrategyTemplate).where(StrategyTemplate.code == "rsi_layered")
                        )
                    ).scalar_one()
                    return inserted, updated, t.name, t.is_active
            finally:
                await engine.dispose()

        inserted, updated, name, is_active = asyncio.run(go())
        assert inserted == 0
        assert updated >= 1  # 至少 rsi_layered 被改
        assert name == "RSI 分层极值追踪"  # 恢复
        assert is_active is True  # 恢复

    def test_upsert_does_not_remove_unknown_codes(self):
        """DB 里有 STRATEGY_TEMPLATES 不包含的 code(用户手加) → 应保留"""

        async def go():
            engine, session_factory = await _build_in_memory_session()
            try:
                # 手动插一条非种子模板
                async with session_factory() as s:
                    from app.models.strategy import StrategyTemplate

                    s.add(
                        StrategyTemplate(
                            code="user_custom_zzz",
                            name="用户手加",
                            description="测试用",
                            strategy_type="ma",
                            risk_level="low",
                            params_schema={"params": []},
                            is_active=True,
                        )
                    )
                    await s.commit()
                # upsert
                async with session_factory() as s:
                    await upsert_strategy_templates(s)
                    await s.commit()
                # 验证手加的还在
                async with session_factory() as s:
                    from sqlalchemy import select

                    from app.models.strategy import StrategyTemplate

                    rows = (await s.execute(select(StrategyTemplate))).scalars().all()
                    return [r.code for r in rows]
            finally:
                await engine.dispose()

        codes = asyncio.run(go())
        assert "user_custom_zzz" in codes  # 保留
        assert "rsi_layered" in codes  # 种子也插入了

    def test_upsert_inserts_new_template_after_existing(self):
        """模拟"加新模板"场景:先 seed 一份旧的(只有 5 个),
        再 STRATEGY_TEMPLATES 含 7 个时再 upsert,应只插入 2 个。"""

        async def go():
            engine, session_factory = await _build_in_memory_session()
            try:
                # 先插 5 条(模拟旧版本)
                async with session_factory() as s:
                    from app.models.strategy import StrategyTemplate

                    for tmpl in STRATEGY_TEMPLATES[:5]:
                        s.add(
                            StrategyTemplate(
                                code=tmpl["code"],
                                name=tmpl["name"],
                                description=tmpl["description"],
                                strategy_type=tmpl["strategy_type"],
                                risk_level=tmpl["risk_level"],
                                params_schema=tmpl["params_schema"],
                                is_active=True,
                            )
                        )
                    await s.commit()
                # 现在 upsert(STRATEGY_TEMPLATES 是完整列表)
                async with session_factory() as s:
                    inserted, updated = await upsert_strategy_templates(s)
                    await s.commit()
                return inserted, updated
            finally:
                await engine.dispose()

        inserted, updated = asyncio.run(go())
        # 应只插入差额条数,且不更新已有 5 条
        assert inserted == len(STRATEGY_TEMPLATES) - 5
        assert updated == 0
