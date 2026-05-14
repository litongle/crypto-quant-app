"""
数据初始化脚本 - 初始化策略模板数据
"""

import asyncio
import logging

from app.database import get_session_maker
from app.database import init_db as db_init_db
from app.models.strategy import StrategyTemplate

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────
# 共用参数:K 线周期
# 决定策略实时下单的轮询节奏 + 回测使用的 K 线粒度。
# 实时下单从 strategy_runner 读取此字段;回测从 backtest_service 读取此字段。
# 二者一致才能保证回测和实盘的策略行为对齐。
# ────────────────────────────────────────────────────────────
_KLINE_INTERVAL_PARAM = {
    "key": "kline_interval",
    "name": "K线周期",
    "type": "select",
    "default": "1h",
    "options": [
        {"value": "1m", "label": "1 分钟"},
        {"value": "5m", "label": "5 分钟"},
        {"value": "15m", "label": "15 分钟"},
        {"value": "30m", "label": "30 分钟"},
        {"value": "1h", "label": "1 小时"},
        {"value": "4h", "label": "4 小时"},
        {"value": "1d", "label": "日线"},
    ],
    "description": (
        "策略实时下单和回测共用的 K 线周期。"
        "周期越短信号越频繁,但更易被市场噪声触发;周期越长越稳但反应慢。"
        "回测和实盘必须一致,否则同一组参数表现会完全不同。"
    ),
}

_AUTO_TRADE_PARAM = {
    "key": "auto_trade",
    "name": "自动下单(谨慎)",
    "type": "bool",
    "default": False,
    "description": "开启后产生信号会真实下单(需绑定交易所账户),关闭则只持久化信号",
}


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
                _KLINE_INTERVAL_PARAM,
                {
                    "key": "fastPeriod",
                    "name": "快线周期",
                    "type": "int",
                    "default": 5,
                    "min": 2,
                    "max": 50,
                    "step": 1,
                },
                {
                    "key": "slowPeriod",
                    "name": "慢线周期",
                    "type": "int",
                    "default": 20,
                    "min": 5,
                    "max": 200,
                    "step": 1,
                },
                _AUTO_TRADE_PARAM,
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
                _KLINE_INTERVAL_PARAM,
                {
                    "key": "period",
                    "name": "RSI周期",
                    "type": "int",
                    "default": 14,
                    "min": 5,
                    "max": 50,
                    "step": 1,
                },
                {
                    "key": "oversold",
                    "name": "超卖线",
                    "type": "int",
                    "default": 30,
                    "min": 10,
                    "max": 40,
                    "step": 1,
                },
                {
                    "key": "overbought",
                    "name": "超买线",
                    "type": "int",
                    "default": 70,
                    "min": 60,
                    "max": 90,
                    "step": 1,
                },
                _AUTO_TRADE_PARAM,
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
                _KLINE_INTERVAL_PARAM,
                {
                    "key": "period",
                    "name": "周期",
                    "type": "int",
                    "default": 20,
                    "min": 10,
                    "max": 50,
                    "step": 1,
                },
                {
                    "key": "stdDev",
                    "name": "标准差倍数",
                    "type": "double",
                    "default": 2.0,
                    "min": 1.0,
                    "max": 4.0,
                    "step": 0.5,
                },
                _AUTO_TRADE_PARAM,
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
                _KLINE_INTERVAL_PARAM,
                {
                    "key": "gridCount",
                    "name": "网格数量",
                    "type": "int",
                    "default": 10,
                    "min": 5,
                    "max": 50,
                    "step": 1,
                },
                {
                    "key": "investmentPerGrid",
                    "name": "每格投入(USDT)",
                    "type": "double",
                    "default": 100,
                    "min": 10,
                    "max": 10000,
                    "step": 10,
                },
                {
                    "key": "priceRange",
                    "name": "价格范围(%)",
                    "type": "double",
                    "default": 10,
                    "min": 1,
                    "max": 50,
                    "step": 1,
                },
                _AUTO_TRADE_PARAM,
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
                _KLINE_INTERVAL_PARAM,
                {
                    "key": "initialInvestment",
                    "name": "初始投资(USDT)",
                    "type": "double",
                    "default": 100,
                    "min": 10,
                    "max": 1000,
                    "step": 10,
                },
                {
                    "key": "multiplier",
                    "name": "倍数",
                    "type": "double",
                    "default": 2.0,
                    "min": 1.5,
                    "max": 3.0,
                    "step": 0.1,
                },
                {
                    "key": "maxLosses",
                    "name": "最大连续亏损",
                    "type": "int",
                    "default": 5,
                    "min": 2,
                    "max": 10,
                    "step": 1,
                },
                _AUTO_TRADE_PARAM,
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
                _KLINE_INTERVAL_PARAM,
                {
                    "key": "rules",
                    "name": "交易规则",
                    "type": "rules",
                    "default": None,
                    "description": "JSON 规则定义，含 buy_rules/sell_rules/risk",
                },
                _AUTO_TRADE_PARAM,
            ],
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
            # 前端规则构建器使用的指标元数据
            "indicators": [
                {"key": "price", "name": "价格", "type": "value", "params": []},
                {
                    "key": "rsi",
                    "name": "RSI",
                    "type": "value",
                    "params": [
                        {
                            "key": "period",
                            "name": "周期",
                            "default": 14,
                            "type": "int",
                            "min": 2,
                            "max": 50,
                        }
                    ],
                },
                {
                    "key": "ma",
                    "name": "均线MA",
                    "type": "value",
                    "params": [
                        {
                            "key": "period",
                            "name": "周期",
                            "default": 20,
                            "type": "int",
                            "min": 2,
                            "max": 200,
                        }
                    ],
                },
                {
                    "key": "ema",
                    "name": "指数均线EMA",
                    "type": "value",
                    "params": [
                        {
                            "key": "period",
                            "name": "周期",
                            "default": 20,
                            "type": "int",
                            "min": 2,
                            "max": 200,
                        }
                    ],
                },
                {
                    "key": "ma_cross",
                    "name": "均线交叉",
                    "type": "event",
                    "params": [
                        {
                            "key": "fast_period",
                            "name": "快线周期",
                            "default": 5,
                            "type": "int",
                            "min": 2,
                            "max": 50,
                        },
                        {
                            "key": "slow_period",
                            "name": "慢线周期",
                            "default": 20,
                            "type": "int",
                            "min": 5,
                            "max": 200,
                        },
                    ],
                },
                {
                    "key": "bollinger_upper",
                    "name": "布林上轨",
                    "type": "value",
                    "params": [
                        {
                            "key": "period",
                            "name": "周期",
                            "default": 20,
                            "type": "int",
                            "min": 5,
                            "max": 50,
                        },
                        {
                            "key": "std_dev",
                            "name": "标准差",
                            "default": 2.0,
                            "type": "double",
                            "min": 1.0,
                            "max": 4.0,
                        },
                    ],
                },
                {
                    "key": "bollinger_lower",
                    "name": "布林下轨",
                    "type": "value",
                    "params": [
                        {
                            "key": "period",
                            "name": "周期",
                            "default": 20,
                            "type": "int",
                            "min": 5,
                            "max": 50,
                        },
                        {
                            "key": "std_dev",
                            "name": "标准差",
                            "default": 2.0,
                            "type": "double",
                            "min": 1.0,
                            "max": 4.0,
                        },
                    ],
                },
                {
                    "key": "bollinger_pct",
                    "name": "布林位置%",
                    "type": "value",
                    "params": [
                        {
                            "key": "period",
                            "name": "周期",
                            "default": 20,
                            "type": "int",
                            "min": 5,
                            "max": 50,
                        },
                        {
                            "key": "std_dev",
                            "name": "标准差",
                            "default": 2.0,
                            "type": "double",
                            "min": 1.0,
                            "max": 4.0,
                        },
                    ],
                },
                {"key": "volume", "name": "成交量", "type": "value", "params": []},
                {
                    "key": "volume_ma",
                    "name": "成交量均线",
                    "type": "value",
                    "params": [
                        {
                            "key": "period",
                            "name": "周期",
                            "default": 20,
                            "type": "int",
                            "min": 2,
                            "max": 100,
                        }
                    ],
                },
                {
                    "key": "atr",
                    "name": "ATR波幅",
                    "type": "value",
                    "params": [
                        {
                            "key": "period",
                            "name": "周期",
                            "default": 14,
                            "type": "int",
                            "min": 2,
                            "max": 50,
                        }
                    ],
                },
                {
                    "key": "macd",
                    "name": "MACD柱",
                    "type": "value",
                    "params": [
                        {
                            "key": "fast",
                            "name": "快线",
                            "default": 12,
                            "type": "int",
                            "min": 2,
                            "max": 50,
                        },
                        {
                            "key": "slow",
                            "name": "慢线",
                            "default": 26,
                            "type": "int",
                            "min": 5,
                            "max": 100,
                        },
                        {
                            "key": "signal",
                            "name": "信号线",
                            "default": 9,
                            "type": "int",
                            "min": 2,
                            "max": 50,
                        },
                    ],
                },
                {
                    "key": "macd_cross",
                    "name": "MACD交叉",
                    "type": "event",
                    "params": [
                        {
                            "key": "fast",
                            "name": "快线",
                            "default": 12,
                            "type": "int",
                            "min": 2,
                            "max": 50,
                        },
                        {
                            "key": "slow",
                            "name": "慢线",
                            "default": 26,
                            "type": "int",
                            "min": 5,
                            "max": 100,
                        },
                        {
                            "key": "signal",
                            "name": "信号线",
                            "default": 9,
                            "type": "int",
                            "min": 2,
                            "max": 50,
                        },
                    ],
                },
                {
                    "key": "price_change_pct",
                    "name": "涨跌幅%",
                    "type": "value",
                    "params": [
                        {
                            "key": "period",
                            "name": "K线数",
                            "default": 1,
                            "type": "int",
                            "min": 1,
                            "max": 50,
                        }
                    ],
                },
                {
                    "key": "stoch_k",
                    "name": "KDJ-K值",
                    "type": "value",
                    "params": [
                        {
                            "key": "period",
                            "name": "周期",
                            "default": 14,
                            "type": "int",
                            "min": 2,
                            "max": 50,
                        }
                    ],
                },
                {
                    "key": "cci",
                    "name": "CCI",
                    "type": "value",
                    "params": [
                        {
                            "key": "period",
                            "name": "周期",
                            "default": 20,
                            "type": "int",
                            "min": 5,
                            "max": 50,
                        }
                    ],
                },
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
                _KLINE_INTERVAL_PARAM,
                {
                    "key": "rsi_period",
                    "name": "RSI 周期",
                    "type": "int",
                    "default": 14,
                    "min": 5,
                    "max": 50,
                    "step": 1,
                },
                {
                    "key": "long_levels",
                    "name": "多头三层阈值",
                    "type": "array_int",
                    "default": [30, 25, 20],
                    "description": "RSI 跌破第 1/2/3 层后开始追踪极值,逗号分隔,从浅到深",
                },
                {
                    "key": "short_levels",
                    "name": "空头三层阈值",
                    "type": "array_int",
                    "default": [70, 75, 80],
                    "description": "RSI 突破第 1/2/3 层后开始追踪极值,逗号分隔,从浅到深",
                },
                {
                    "key": "retracement_points",
                    "name": "极值回撤触发(点)",
                    "type": "double",
                    "default": 2.0,
                    "min": 0.5,
                    "max": 10.0,
                    "step": 0.5,
                },
                {
                    "key": "max_additional_positions",
                    "name": "最大加仓次数",
                    "type": "int",
                    "default": 4,
                    "min": 0,
                    "max": 10,
                    "step": 1,
                },
                {
                    "key": "size_mode",
                    "name": "止损止盈量纲",
                    "type": "select",
                    "default": "pct",
                    "options": [
                        {"value": "pct", "label": "按入场价百分比"},
                        {"value": "atr", "label": "按 ATR 倍数"},
                    ],
                    "description": (
                        "决定下方止损/止盈阈值的换算方式。"
                        "pct：阈值=入场价×百分比，跨币种、跨价位都自适应，配置直观。"
                        "atr：阈值=入场时锁定的 ATR×倍数，按当下波动率自适应，更专业。"
                    ),
                },
                {
                    "key": "fixed_stop_loss_pct",
                    "name": "固定止损（百分比）",
                    "type": "double",
                    "default": 0.005,
                    "min": 0.001,
                    "max": 0.10,
                    "step": 0.001,
                    "description": "size_mode=pct 时生效。0.005 表示浮亏达到入场价 0.5% 平仓。",
                },
                {
                    "key": "profit_taking_config_pct",
                    "name": "分层浮动止盈（百分比）",
                    "type": "json_table",
                    "default": [[10, 0.003, 0.002], [30, 0.005, 0.003], [60, 0.010, 0.005]],
                    "columns": [
                        {
                            "key": "window",
                            "name": "持仓 K 线数 ≥",
                            "type": "int",
                            "min": 1,
                            "step": 1,
                        },
                        {
                            "key": "drawdown",
                            "name": "最大浮盈回撤 ≥",
                            "type": "double",
                            "step": 0.001,
                            "suffix": "（小数；0.005 = 0.5%）",
                        },
                        {
                            "key": "min_profit",
                            "name": "当前浮盈 ≥",
                            "type": "double",
                            "step": 0.001,
                            "suffix": "（小数；0.002 = 0.2%）",
                        },
                    ],
                    "description": (
                        "size_mode=pct 时生效。每行一档「持仓 K 线数 / 回撤阈值 / 最低盈利阈值」，"
                        "三者同时满足才平仓。建议自下而上递增——越后期越宽松。"
                    ),
                },
                {
                    "key": "atr_period",
                    "name": "ATR 周期",
                    "type": "int",
                    "default": 14,
                    "min": 5,
                    "max": 100,
                    "step": 1,
                    "description": "size_mode=atr 时生效。ATR 计算所用的 K 线根数。",
                },
                {
                    "key": "fixed_stop_loss_atr",
                    "name": "固定止损（ATR 倍数）",
                    "type": "double",
                    "default": 2.0,
                    "min": 0.5,
                    "max": 10.0,
                    "step": 0.1,
                    "description": (
                        "size_mode=atr 时生效。开仓时锁定 ATR，止损阈值=ATR×本倍数。"
                        "锁定可避免波动飙升时止损被反向推远。"
                    ),
                },
                {
                    "key": "profit_taking_config_atr",
                    "name": "分层浮动止盈（ATR 倍数）",
                    "type": "json_table",
                    "default": [[10, 1.0, 0.7], [30, 1.5, 1.0], [60, 3.0, 1.5]],
                    "columns": [
                        {
                            "key": "window",
                            "name": "持仓 K 线数 ≥",
                            "type": "int",
                            "min": 1,
                            "step": 1,
                        },
                        {
                            "key": "drawdown",
                            "name": "最大浮盈回撤 ≥",
                            "type": "double",
                            "step": 0.1,
                            "suffix": "× ATR",
                        },
                        {
                            "key": "min_profit",
                            "name": "当前浮盈 ≥",
                            "type": "double",
                            "step": 0.1,
                            "suffix": "× ATR",
                        },
                    ],
                    "description": (
                        "size_mode=atr 时生效。每行一档「持仓 K 线数 / 回撤倍数 / 最低盈利倍数」，"
                        "倍数单位是入场时锁定的 ATR，三者同时满足才平仓。"
                    ),
                },
                {
                    "key": "max_holding_candles",
                    "name": "最大持仓 K 线数",
                    "type": "int",
                    "default": 60,
                    "min": 5,
                    "max": 500,
                    "step": 5,
                },
                {
                    "key": "cooling_candles",
                    "name": "平仓后冷却 K 线",
                    "type": "int",
                    "default": 3,
                    "min": 0,
                    "max": 50,
                    "step": 1,
                },
                {
                    "key": "max_invest_percent",
                    "name": "单笔最大资金比例(%)",
                    "type": "double",
                    "default": 30,
                    "min": 1,
                    "max": 95,
                    "description": "与实盘 runner 一致：每笔下单最多占用当前可用余额的比例。",
                },
                {
                    "key": "leverage",
                    "name": "合约杠杆(倍)",
                    "type": "int",
                    "default": 20,
                    "min": 1,
                    "max": 125,
                    "description": "回测永续时用于推导初始保证金率 1/杠杆（可被下方 initial_margin_rate 覆盖）。",
                },
                {
                    "key": "initial_margin_rate",
                    "name": "初始保证金率(小数)",
                    "type": "double",
                    "default": 0,
                    "min": 0,
                    "max": 1,
                    "description": "0 表示按 1/杠杆 计算；例如 0.05=名义本金的 5% 作为初始保证金。",
                },
                {
                    "key": "funding_rate_8h",
                    "name": "资金费率(每期)",
                    "type": "double",
                    "default": 0,
                    "min": -0.01,
                    "max": 0.01,
                    "description": (
                        "每期(UTC 约 8h 一档)名义价值×费率；与 Binance 符号一致：正=多付空收。"
                        "0=回测不计资金费。"
                    ),
                },
                {
                    **_AUTO_TRADE_PARAM,
                },
            ],
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        },
    },
    {
        "code": "dca",
        "name": "DCA 定投策略",
        "description": "定期定额投资策略，支持智能定投（RSI低时加大投入）。适合长期持有，降低择时风险。",
        "strategy_type": "dca",
        "risk_level": "conservative",
        "params_schema": {
            "params": [
                _KLINE_INTERVAL_PARAM,
                {
                    "key": "dca_interval_candles",
                    "name": "定投间隔(K线数)",
                    "type": "int",
                    "default": 24,
                    "min": 1,
                    "max": 168,
                    "step": 1,
                    "description": "1h K线时 24=每天1次, 168=每周1次",
                },
                {
                    "key": "invest_per_trade",
                    "name": "每次定投金额(USDT)",
                    "type": "double",
                    "default": 100,
                    "min": 10,
                    "max": 10000,
                    "step": 10,
                },
                {
                    "key": "smart_dca",
                    "name": "智能定投",
                    "type": "bool",
                    "default": False,
                    "description": "RSI超卖时定投额放大50%，超买时缩减50%",
                },
                {
                    "key": "take_profit_pct",
                    "name": "止盈比例(%)",
                    "type": "double",
                    "default": 20,
                    "min": 5,
                    "max": 100,
                    "step": 5,
                },
                {
                    "key": "stop_loss_pct",
                    "name": "止损比例(%)",
                    "type": "double",
                    "default": 30,
                    "min": 5,
                    "max": 50,
                    "step": 5,
                },
                _AUTO_TRADE_PARAM,
            ],
            "symbols": ["BTCUSDT", "ETHUSDT"],
        },
    },
    {
        "code": "multi_symbol",
        "name": "多币种联动策略",
        "description": "支持Leader-Follow模式和配对交易。主币种信号联动从币种，或利用两币价差回归套利。",
        "strategy_type": "multi_symbol",
        "risk_level": "high",
        "params_schema": {
            "params": [
                _KLINE_INTERVAL_PARAM,
                {
                    "key": "mode",
                    "name": "策略模式",
                    "type": "select",
                    "default": "leader_follow",
                    "options": [
                        {"value": "leader_follow", "label": "Leader-Follow 联动"},
                        {"value": "pair_trading", "label": "配对交易"},
                    ],
                },
                {
                    "key": "leader_symbol",
                    "name": "主交易对",
                    "type": "select",
                    "default": "BTCUSDT",
                    "options": [
                        {"value": "BTCUSDT", "label": "BTC/USDT"},
                        {"value": "ETHUSDT", "label": "ETH/USDT"},
                    ],
                },
                {
                    "key": "follower_symbols",
                    "name": "跟随交易对",
                    "type": "json",
                    "default": ["ETHUSDT"],
                    "description": "Leader-Follow 模式下联动交易对（JSON数组）",
                },
                {
                    "key": "pair_symbol",
                    "name": "配对交易对",
                    "type": "select",
                    "default": "ETHUSDT",
                    "options": [
                        {"value": "ETHUSDT", "label": "ETH/USDT"},
                        {"value": "SOLUSDT", "label": "SOL/USDT"},
                    ],
                },
                {
                    "key": "entry_zscore",
                    "name": "入场Z分数",
                    "type": "double",
                    "default": 2.0,
                    "min": 1.0,
                    "max": 5.0,
                    "step": 0.5,
                    "description": "价差Z分数超过此值开仓",
                },
                {
                    "key": "exit_zscore",
                    "name": "出场Z分数",
                    "type": "double",
                    "default": 0.5,
                    "min": 0.1,
                    "max": 2.0,
                    "step": 0.1,
                    "description": "价差Z分数回归此值平仓",
                },
            ],
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        },
    },
]


UPSERT_FIELDS = ("name", "description", "strategy_type", "risk_level", "params_schema")


async def upsert_strategy_templates(session) -> tuple[int, int]:
    """按 code upsert STRATEGY_TEMPLATES 到 session(不 commit)。

    - code 已存在 → 更新 name / description / strategy_type / risk_level /
      params_schema 五个字段(以及 is_active=True)
    - code 不存在 → INSERT
    - 不删除 DB 里有但 STRATEGY_TEMPLATES 没的(用户可能手动加了模板),
      想清空请手动 DELETE 后重启

    幂等:多次调用结果一致,可放在每次应用启动时跑。

    Returns:
        (inserted, updated)
    """
    from sqlalchemy import select

    result = await session.execute(select(StrategyTemplate))
    existing_by_code = {t.code: t for t in result.scalars().all()}

    inserted = 0
    updated = 0

    for tmpl_data in STRATEGY_TEMPLATES:
        code = tmpl_data["code"]
        existing = existing_by_code.get(code)

        if existing is None:
            session.add(
                StrategyTemplate(
                    code=code,
                    name=tmpl_data["name"],
                    description=tmpl_data["description"],
                    strategy_type=tmpl_data["strategy_type"],
                    risk_level=tmpl_data["risk_level"],
                    params_schema=tmpl_data["params_schema"],
                    is_active=True,
                )
            )
            inserted += 1
        else:
            changed = False
            for field in UPSERT_FIELDS:
                new_val = tmpl_data[field]
                if getattr(existing, field) != new_val:
                    setattr(existing, field, new_val)
                    changed = True
            if not existing.is_active:
                existing.is_active = True
                changed = True
            if changed:
                updated += 1

    return inserted, updated


async def init_strategy_templates():
    """初始化/更新策略模板(应用启动时调用)。

    采用 upsert 而非"已有数据就跳过":
      · 加新策略模板 → 重启应用即生效
      · 改 params_schema/描述 → 重启应用即生效
      · 删除模板需要手工 DELETE FROM strategy_templates WHERE code='...'
    """
    session_maker = await get_session_maker()
    async with session_maker() as session:
        inserted, updated = await upsert_strategy_templates(session)
        await session.commit()
        logger.info(
            "策略模板 upsert 完成: 新增 %d, 更新 %d, 总计 %d",
            inserted,
            updated,
            len(STRATEGY_TEMPLATES),
        )


async def init_db():
    """初始化数据库"""
    await db_init_db()
    logger.info("数据库表创建完成")


if __name__ == "__main__":
    asyncio.run(init_db())
    asyncio.run(init_strategy_templates())
