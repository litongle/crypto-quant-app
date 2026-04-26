"""
全局常量定义
"""

# 策略 code → 数据库整数 template_id 映射
# P1-8: 统一策略 ID 映射，避免重复定义和不一致
STR_ID_MAP = {
    "ma_cross": 1,
    "rsi": 2,
    "bollinger": 3,
    "grid": 4,
    "martingale": 5,
    "rule_custom": 6,
}

# 反向映射：数据库 template_id (int) → 前端 code (str)
TEMPLATE_ID_TO_CODE = {v: k for k, v in STR_ID_MAP.items()}
