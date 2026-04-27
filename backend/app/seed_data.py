"""
数据初始化脚本 - 初始化策略模板数据
"""
import asyncio
import logging
from decimal import Decimal

from app.database import get_session_maker, Base, init_db as db_init_db
from app.models.strategy import StrategyTemplate

logger = logging.getLogger(__name__)


# 预定义策略模板
STRATEGY_TEMPLATES = [
    {
        "code": "ma_cross",
        "name": "双均线策略",
        "description": "短期均线上穿长期均线买入，下穿卖出。趋势跟踪策略，适合趋势明显的行情。",
        "strategy_type": "ma",
        "risk_level": "medium",
        "params_schema": {
            "params": [
                {"key": "fastPeriod", "name": "快线周期", "type": "int", "default": 5, "min": 2, "max": 50, "step": 1},
                {"key": "slowPeriod", "name": "慢线周期", "type": "int", "default": 20, "min": 5, "max": 200, "step": 1},
            ],
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        },
    },
    {
        "code": "rsi",
        "name": "RSI策略",
        "description": "RSI超卖时买入，超买时卖出。均值回归策略，适合震荡行情。",
        "strategy_type": "rsi",
        "risk_level": "medium",
        "params_schema": {
            "params": [
                {"key": "period", "name": "RSI周期", "type": "int", "default": 14, "min": 5, "max": 50, "step": 1},
                {"key": "oversold", "name": "超卖线", "type": "int", "default": 30, "min": 10, "max": 40, "step": 1},
                {"key": "overbought", "name": "超买线", "type": "int", "default": 70, "min": 60, "max": 90, "step": 1},
            ],
            "symbols": ["BTCUSDT", "ETHUSDT"],
        },
    },
    {
        "code": "bollinger",
        "name": "布林带策略",
        "description": "价格触及下轨买入，触及上轨卖出。波动率策略，适合高波动行情。",
        "strategy_type": "bollinger",
        "risk_level": "high",
        "params_schema": {
            "params": [
                {"key": "period", "name": "周期", "type": "int", "default": 20, "min": 10, "max": 50, "step": 1},
                {"key": "stdDev", "name": "标准差倍数", "type": "double", "default": 2.0, "min": 1.0, "max": 4.0, "step": 0.5},
            ],
            "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
        },
    },
    {
        "code": "grid",
        "name": "网格策略",
        "description": "在固定价格区间内低买高卖，反复套利。适合震荡行情。",
        "strategy_type": "grid",
        "risk_level": "medium",
        "params_schema": {
            "params": [
                {"key": "gridCount", "name": "网格数量", "type": "int", "default": 10, "min": 5, "max": 50, "step": 1},
                {"key": "investmentPerGrid", "name": "每格投入(USDT)", "type": "double", "default": 100, "min": 10, "max": 10000, "step": 10},
                {"key": "priceRange", "name": "价格范围(%)", "type": "double", "default": 10, "min": 1, "max": 50, "step": 1},
            ],
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        },
    },
    {
        "code": "martingale",
        "name": "马丁格尔策略",
        "description": "亏损后加倍下单，盈利后回归初始仓位。高风险，适合大户。",
        "strategy_type": "martingale",
        "risk_level": "high",
        "params_schema": {
            "params": [
                {"key": "initialInvestment", "name": "初始投资(USDT)", "type": "double", "default": 100, "min": 10, "max": 1000, "step": 10},
                {"key": "multiplier", "name": "倍数", "type": "double", "default": 2.0, "min": 1.5, "max": 3.0, "step": 0.1},
                {"key": "maxLosses", "name": "最大连续亏损", "type": "int", "default": 5, "min": 2, "max": 10, "step": 1},
            ],
            "symbols": ["BTCUSDT", "ETHUSDT"],
        },
    },
    {
        "code": "rule_custom",
        "name": "自定义规则策略",
        "description": "通过组合技术指标条件创建自定义策略，无需编程。支持 RSI/MA/布林带/MACD 等 14 种指标，AND/OR 逻辑组合。",
        "strategy_type": "rule",
        "risk_level": "medium",
        "params_schema": {
            "params": [
                {
                    "key": "rules",
                    "name": "交易规则",
                    "type": "rules",
                    "default": None,
                    "description": "JSON 规则定义，含 buy_rules/sell_rules/risk",
                },
            ],
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
            # 前端规则构建器使用的指标元数据
            "indicators": [
                {"key": "price", "name": "价格", "type": "value", "params": []},
                {"key": "rsi", "name": "RSI", "type": "value", "params": [{"key": "period", "name": "周期", "default": 14, "type": "int", "min": 2, "max": 50}]},
                {"key": "ma", "name": "均线MA", "type": "value", "params": [{"key": "period", "name": "周期", "default": 20, "type": "int", "min": 2, "max": 200}]},
                {"key": "ema", "name": "指数均线EMA", "type": "value", "params": [{"key": "period", "name": "周期", "default": 20, "type": "int", "min": 2, "max": 200}]},
                {"key": "ma_cross", "name": "均线交叉", "type": "event", "params": [
                    {"key": "fast_period", "name": "快线周期", "default": 5, "type": "int", "min": 2, "max": 50},
                    {"key": "slow_period", "name": "慢线周期", "default": 20, "type": "int", "min": 5, "max": 200},
                ]},
                {"key": "bollinger_upper", "name": "布林上轨", "type": "value", "params": [
                    {"key": "period", "name": "周期", "default": 20, "type": "int", "min": 5, "max": 50},
                    {"key": "std_dev", "name": "标准差", "default": 2.0, "type": "double", "min": 1.0, "max": 4.0},
                ]},
                {"key": "bollinger_lower", "name": "布林下轨", "type": "value", "params": [
                    {"key": "period", "name": "周期", "default": 20, "type": "int", "min": 5, "max": 50},
                    {"key": "std_dev", "name": "标准差", "default": 2.0, "type": "double", "min": 1.0, "max": 4.0},
                ]},
                {"key": "bollinger_pct", "name": "布林位置%", "type": "value", "params": [
                    {"key": "period", "name": "周期", "default": 20, "type": "int", "min": 5, "max": 50},
                    {"key": "std_dev", "name": "标准差", "default": 2.0, "type": "double", "min": 1.0, "max": 4.0},
                ]},
                {"key": "volume", "name": "成交量", "type": "value", "params": []},
                {"key": "volume_ma", "name": "成交量均线", "type": "value", "params": [{"key": "period", "name": "周期", "default": 20, "type": "int", "min": 2, "max": 100}]},
                {"key": "atr", "name": "ATR波幅", "type": "value", "params": [{"key": "period", "name": "周期", "default": 14, "type": "int", "min": 2, "max": 50}]},
                {"key": "macd", "name": "MACD柱", "type": "value", "params": [
                    {"key": "fast", "name": "快线", "default": 12, "type": "int", "min": 2, "max": 50},
                    {"key": "slow", "name": "慢线", "default": 26, "type": "int", "min": 5, "max": 100},
                    {"key": "signal", "name": "信号线", "default": 9, "type": "int", "min": 2, "max": 50},
                ]},
                {"key": "macd_cross", "name": "MACD交叉", "type": "event", "params": [
                    {"key": "fast", "name": "快线", "default": 12, "type": "int", "min": 2, "max": 50},
                    {"key": "slow", "name": "慢线", "default": 26, "type": "int", "min": 5, "max": 100},
                    {"key": "signal", "name": "信号线", "default": 9, "type": "int", "min": 2, "max": 50},
                ]},
                {"key": "price_change_pct", "name": "涨跌幅%", "type": "value", "params": [{"key": "period", "name": "K线数", "default": 1, "type": "int", "min": 1, "max": 50}]},
                {"key": "stoch_k", "name": "KDJ-K值", "type": "value", "params": [{"key": "period", "name": "周期", "default": 14, "type": "int", "min": 2, "max": 50}]},
                {"key": "cci", "name": "CCI", "type": "value", "params": [{"key": "period", "name": "周期", "default": 20, "type": "int", "min": 5, "max": 50}]},
            ],
        },
    },
    {
        "code": "rsi_layered",
        "name": "RSI 分层极值追踪",
        "description": (
            "进阶 RSI 策略：监控 RSI 进入超买/超卖三层阈值,追踪区间极值,"
            "回撤触发开仓。支持加仓/分层浮动止盈/固定止损/超时平仓/反手交易/"
            "冷却期。可重启不丢仓位状态。"
        ),
        "strategy_type": "rsi_layered",
        "risk_level": "high",
        "params_schema": {
            "params": [
                {"key": "rsi_period", "name": "RSI 周期", "type": "int",
                 "default": 14, "min": 5, "max": 50, "step": 1},
                {"key": "long_levels", "name": "多头三层阈值",
                 "type": "array_int", "default": [30, 25, 20],
                 "description": "RSI 跌破第 1/2/3 层后开始追踪极值,逗号分隔,从浅到深"},
                {"key": "short_levels", "name": "空头三层阈值",
                 "type": "array_int", "default": [70, 75, 80],
                 "description": "RSI 突破第 1/2/3 层后开始追踪极值,逗号分隔,从浅到深"},
                {"key": "retracement_points", "name": "极值回撤触发(点)",
                 "type": "double", "default": 2.0, "min": 0.5, "max": 10.0, "step": 0.5},
                {"key": "max_additional_positions", "name": "最大加仓次数",
                 "type": "int", "default": 4, "min": 0, "max": 10, "step": 1},
                {"key": "fixed_stop_loss_points", "name": "固定止损(价格点)",
                 "type": "double", "default": 6.0, "min": 1.0, "max": 100.0, "step": 1.0},
                {"key": "max_holding_candles", "name": "最大持仓 K 线数",
                 "type": "int", "default": 60, "min": 5, "max": 500, "step": 5},
                {"key": "cooling_candles", "name": "平仓后冷却 K 线",
                 "type": "int", "default": 3, "min": 0, "max": 50, "step": 1},
                {"key": "profit_taking_config", "name": "分层浮动止盈",
                 "type": "json", "default": [[10, 3.0, 2.0], [30, 5.0, 3.0], [60, 10.0, 5.0]],
                 "description": "[[窗口K线数, 回撤点数, 最小盈利], ...]"},
                {"key": "auto_trade", "name": "自动下单(谨慎)",
                 "type": "bool", "default": False,
                 "description": "开启后产生信号会真实下单(需绑定交易所账户),关闭则只持久化信号"},
            ],
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        },
    },
]


async def init_strategy_templates():
    """初始化策略模板数据"""
    session_maker = await get_session_maker()
    async with session_maker() as session:
        # 检查是否已有数据
        from sqlalchemy import select
        result = await session.execute(select(StrategyTemplate))
        existing = result.scalars().first()

        if existing:
            logger.info("策略模板已存在，跳过初始化")
            return

        # 创建模板
        templates = []
        for template_data in STRATEGY_TEMPLATES:
            template = StrategyTemplate(
                code=template_data["code"],
                name=template_data["name"],
                description=template_data["description"],
                strategy_type=template_data["strategy_type"],
                risk_level=template_data["risk_level"],
                params_schema=template_data["params_schema"],
                is_active=True,
            )
            templates.append(template)
            session.add(template)

        await session.commit()
        logger.info("成功初始化 %d 个策略模板", len(templates))


async def init_db():
    """初始化数据库"""
    await db_init_db()
    logger.info("数据库表创建完成")


if __name__ == "__main__":
    asyncio.run(init_db())
    asyncio.run(init_strategy_templates())
