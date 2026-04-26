"""
技术指标计算库 — 规则引擎专用

所有函数接收 numpy 数组，返回等长数组（前面不足部分用 NaN 填充），
确保输出与输入 K 线一一对应，rule_engine 按索引取最新值即可。
"""
from typing import Tuple

import numpy as np


# ── 工具函数 ──────────────────────────────────────────────

def _pad_to_length(data: np.ndarray, target_len: int) -> np.ndarray:
    """将短数组前面用 NaN 填充到目标长度"""
    if len(data) >= target_len:
        return data
    pad = np.full(target_len - len(data), np.nan)
    return np.concatenate([pad, data])


# ── 趋势指标 ──────────────────────────────────────────────

def calc_sma(closes: np.ndarray, period: int = 20) -> np.ndarray:
    """简单移动平均 SMA"""
    if len(closes) < period:
        return np.full_like(closes, np.nan)
    result = np.convolve(closes, np.ones(period) / period, mode="valid")
    return _pad_to_length(result, len(closes))


def calc_ema(closes: np.ndarray, period: int = 20) -> np.ndarray:
    """指数移动平均 EMA"""
    if len(closes) < period:
        return np.full_like(closes, np.nan)
    multiplier = 2.0 / (period + 1)
    ema = np.full_like(closes, np.nan, dtype=np.float64)
    ema[period - 1] = np.mean(closes[:period])
    for i in range(period, len(closes)):
        ema[i] = (closes[i] - ema[i - 1]) * multiplier + ema[i - 1]
    return ema


def calc_dema(closes: np.ndarray, period: int = 20) -> np.ndarray:
    """双指数移动平均 DEMA = 2*EMA - EMA(EMA)"""
    ema1 = calc_ema(closes, period)
    # 只对有效部分再算一次 EMA
    valid_start = period - 1
    if valid_start >= len(closes):
        return np.full_like(closes, np.nan)
    ema2 = calc_ema(ema1[valid_start:], period)
    ema2_full = _pad_to_length(ema2, len(closes))
    return 2 * ema1 - ema2_full


# ── 震荡指标 ──────────────────────────────────────────────

def calc_rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """RSI 相对强弱指标 (0-100)"""
    if len(closes) < period + 1:
        return np.full_like(closes, np.nan)
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Wilder 平滑
    avg_gain = np.zeros(len(deltas))
    avg_loss = np.zeros(len(deltas))
    avg_gain[period - 1] = np.mean(gains[:period])
    avg_loss[period - 1] = np.mean(losses[:period])

    for i in range(period, len(deltas)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i]) / period

    rs = avg_gain / (avg_loss + 1e-10)
    rsi_values = 100.0 - (100.0 / (1.0 + rs))

    # deltas 比 closes 少1个元素
    result = np.full(len(closes), np.nan)
    result[period:] = rsi_values[period - 1:]
    return result


def calc_macd(
    closes: np.ndarray,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MACD → (macd_line, signal_line, histogram)"""
    ema_fast = calc_ema(closes, fast)
    ema_slow = calc_ema(closes, slow)
    macd_line = ema_fast - ema_slow

    # 只对有效部分算 signal
    valid_mask = ~np.isnan(macd_line)
    if not np.any(valid_mask):
        empty = np.full_like(closes, np.nan)
        return macd_line, empty.copy(), empty.copy()

    first_valid = np.argmax(valid_mask)
    signal_line = np.full_like(closes, np.nan)
    signal_line[first_valid:] = calc_ema(macd_line[first_valid:], signal)

    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_stoch_k(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """随机指标 K 值"""
    if len(closes) < period:
        return np.full_like(closes, np.nan)
    result = np.full_like(closes, np.nan, dtype=np.float64)
    for i in range(period - 1, len(closes)):
        high_max = np.max(highs[i - period + 1 : i + 1])
        low_min = np.min(lows[i - period + 1 : i + 1])
        diff = high_max - low_min
        result[i] = ((closes[i] - low_min) / diff * 100) if diff != 0 else 50.0
    return result


def calc_stoch_d(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    k_period: int = 14,
    d_period: int = 3,
) -> np.ndarray:
    """随机指标 D 值 (K 的 SMA)"""
    k = calc_stoch_k(highs, lows, closes, k_period)
    return calc_sma(k, d_period)


def calc_cci(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 20,
) -> np.ndarray:
    """CCI 商品通道指标"""
    if len(closes) < period:
        return np.full_like(closes, np.nan)
    tp = (highs + lows + closes) / 3.0
    result = np.full_like(closes, np.nan, dtype=np.float64)
    for i in range(period - 1, len(closes)):
        sma_tp = np.mean(tp[i - period + 1 : i + 1])
        mean_dev = np.mean(np.abs(tp[i - period + 1 : i + 1] - sma_tp))
        result[i] = (tp[i] - sma_tp) / (0.015 * mean_dev) if mean_dev != 0 else 0.0
    return result


# ── 波动率指标 ──────────────────────────────────────────────

def calc_bollinger(
    closes: np.ndarray,
    period: int = 20,
    std_dev: float = 2.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """布林带 → (upper, middle, lower, pct_b)
    pct_b: 价格在布林带中的位置百分比 (0=下轨, 100=上轨)
    """
    middle = calc_sma(closes, period)
    if np.all(np.isnan(middle)):
        empty = np.full_like(closes, np.nan)
        return empty.copy(), middle, empty.copy(), empty.copy()

    std = np.array([
        np.std(closes[max(0, i - period + 1) : i + 1])
        if i >= period - 1 and not np.isnan(middle[i])
        else np.nan
        for i in range(len(closes))
    ])

    upper = middle + std * std_dev
    lower = middle - std * std_dev
    bandwidth = upper - lower
    pct_b = np.where(
        bandwidth != 0,
        (closes - lower) / bandwidth * 100,
        50.0,
    )
    pct_b = np.where(np.isnan(middle), np.nan, pct_b)
    return upper, middle, lower, pct_b


def calc_atr(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """ATR 真实波幅"""
    if len(closes) < 2:
        return np.full_like(closes, np.nan)

    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:] - closes[:-1]),
        ),
    )

    result = np.full(len(closes), np.nan, dtype=np.float64)
    if len(tr) == 0:
        return result

    result[period] = np.mean(tr[:period])  # 第一个 ATR
    for i in range(period, len(tr)):
        idx = i + 1  # 对齐到 closes 索引
        if idx < len(result):
            result[idx] = (result[idx - 1] * (period - 1) + tr[i]) / period
    return result


# ── 成交量指标 ──────────────────────────────────────────────

def calc_volume_ma(volumes: np.ndarray, period: int = 20) -> np.ndarray:
    """成交量均线"""
    return calc_sma(volumes, period)


def calc_obv(closes: np.ndarray, volumes: np.ndarray) -> np.ndarray:
    """OBV 能量潮指标"""
    if len(closes) < 2:
        return np.zeros_like(closes, dtype=np.float64)
    result = np.zeros(len(closes), dtype=np.float64)
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            result[i] = result[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            result[i] = result[i - 1] - volumes[i]
        else:
            result[i] = result[i - 1]
    return result


# ── 价格衍生指标 ──────────────────────────────────────────────

def calc_price_change_pct(closes: np.ndarray, period: int = 1) -> np.ndarray:
    """涨跌幅百分比（相对 period 根前的价格）"""
    if len(closes) <= period:
        return np.full_like(closes, np.nan)
    result = np.full_like(closes, np.nan, dtype=np.float64)
    for i in range(period, len(closes)):
        if closes[i - period] != 0:
            result[i] = (closes[i] - closes[i - period]) / closes[i - period] * 100
    return result


def calc_price(closes: np.ndarray) -> np.ndarray:
    """当前价格（原样返回，方便统一接口）"""
    return closes.copy()
