"""
RSI分层极值追踪自动量化交易系统 - RSI分层极值追踪策略实现

该模块实现了RSI分层极值追踪策略，包括：
- RSI指标计算
- 分层阈值判断
- 极值追踪和回撤检测
- 加仓决策逻辑
- 止盈止损判断
- 分层浮动止盈
- 冷却期管理
- 反手交易逻辑
- 持仓时间管理
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
import time
from enum import Enum

from app.strategy import BaseStrategy, SignalType, StrategyMode
from app.core.config import settings


class RsiLevel(Enum):
    """RSI分层级别枚举"""
    NONE = 0    # 未进入任何层级
    LEVEL1 = 1  # 第一层
    LEVEL2 = 2  # 第二层
    LEVEL3 = 3  # 第三层


class RsiLayeredStrategy(BaseStrategy):
    """
    RSI分层极值追踪策略
    
    核心思想：
    1. 监控RSI进入多头/空头分层阈值区间
    2. 追踪区间内RSI极值
    3. 当RSI从极值回撤指定点数时触发交易信号
    4. 实现加仓、止盈、止损和反手交易逻辑
    """
    
    def __init__(
        self, 
        strategy_id: str, 
        name: str, 
        symbol: str, 
        account_ids: List[int],
        rsi_period: int = 14,
        long_levels: List[int] = None,
        short_levels: List[int] = None,
        retracement_points: int = 2,
        max_additional_positions: int = 4,
        fixed_stop_loss_points: int = 6,
        profit_taking_config: List[Tuple[int, int, int]] = None,
        max_holding_candles: int = 60,
        cooling_candles: int = 3
    ):
        """
        初始化RSI分层极值追踪策略
        
        Args:
            strategy_id: 策略ID
            name: 策略名称
            symbol: 交易对
            account_ids: 关联账户ID列表
            rsi_period: RSI计算周期
            long_levels: 多头分层阈值 [level1, level2, level3]
            short_levels: 空头分层阈值 [level1, level2, level3]
            retracement_points: 极值回撤触发点数
            max_additional_positions: 最大加仓次数
            fixed_stop_loss_points: 固定止损点数
            profit_taking_config: 止盈配置 [(窗口K线数, 回撤点数, 最小盈利), ...]
            max_holding_candles: 最大持仓K线数
            cooling_candles: 平仓后冷却期K线数
        """
        super().__init__(strategy_id, name, symbol, account_ids)
        
        # RSI参数
        self.rsi_period = rsi_period or settings.RSI_PERIOD
        
        # 多头分层阈值
        self.long_levels = long_levels or [
            settings.RSI_LONG_LEVEL1, 
            settings.RSI_LONG_LEVEL2, 
            settings.RSI_LONG_LEVEL3
        ]
        
        # 空头分层阈值
        self.short_levels = short_levels or [
            settings.RSI_SHORT_LEVEL1, 
            settings.RSI_SHORT_LEVEL2, 
            settings.RSI_SHORT_LEVEL3
        ]
        
        # 极值回撤参数
        self.retracement_points = retracement_points or settings.RSI_RETRACEMENT_POINTS
        
        # 加仓参数
        self.max_additional_positions = max_additional_positions or settings.MAX_ADDITIONAL_POSITIONS
        
        # 止损参数
        self.fixed_stop_loss_points = fixed_stop_loss_points or settings.FIXED_STOP_LOSS_POINTS
        
        # 止盈参数
        self.profit_taking_config = profit_taking_config or settings.profit_taking_config
        
        # 持仓管理
        self.max_holding_candles = max_holding_candles or settings.MAX_HOLDING_CANDLES
        self.cooling_candles = cooling_candles or settings.COOLING_CANDLES
        
        # 运行时状态
        self.current_mode = StrategyMode.MONITORING
        self.cooling_count = 0
        
        # 多头监控状态
        self.long_monitoring = False
        self.long_extreme_value = None
        self.long_extreme_time = None
        self.long_level = RsiLevel.NONE
        
        # 空头监控状态
        self.short_monitoring = False
        self.short_extreme_value = None
        self.short_extreme_time = None
        self.short_level = RsiLevel.NONE
        
        # K线历史数据
        self.kline_history = []
        self.rsi_history = []
        
        # 日志配置
        self.logger = logging.getLogger(f"strategy.rsi_layered.{strategy_id}")
        self.logger.info(f"RSI分层极值追踪策略初始化: {self.name} ({self.symbol})")
        self.logger.info(f"多头阈值: {self.long_levels}, 空头阈值: {self.short_levels}")
        self.logger.info(f"回撤点数: {self.retracement_points}, 最大加仓次数: {self.max_additional_positions}")
        self.logger.info(f"止损点数: {self.fixed_stop_loss_points}")
        self.logger.info(f"止盈配置: {self.profit_taking_config}")
        self.logger.info(f"最大持仓K线数: {self.max_holding_candles}, 冷却期: {self.cooling_candles}")
    
    def calculate_rsi(self, close_prices: List[float], period: int = None) -> float:
        """
        计算RSI指标值
        
        Args:
            close_prices: 收盘价列表
            period: RSI周期，默认使用策略配置的周期
            
        Returns:
            float: RSI值
        """
        if period is None:
            period = self.rsi_period
        
        if len(close_prices) < period + 1:
            return 50.0  # 数据不足时返回中性值
        
        # 使用numpy计算RSI，提高性能
        prices = np.array(close_prices)
        deltas = np.diff(prices)
        seed = deltas[:period+1]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        
        if down == 0:
            return 100.0
        
        rs = up / down
        rsi = 100.0 - (100.0 / (1.0 + rs))
        
        # 确保RSI值在0-100之间
        return max(0.0, min(100.0, rsi))
    
    def update_rsi_history(self, kline: Dict[str, Any]) -> float:
        """
        更新RSI历史数据并计算最新RSI值
        
        Args:
            kline: 当前K线数据
            
        Returns:
            float: 最新的RSI值
        """
        try:
            # 添加新的K线数据
            self.kline_history.append(float(kline['close']))
            
            # 保留足够计算RSI的数据量
            max_needed = self.rsi_period * 3  # 保留3倍周期的数据，确保计算准确性
            if len(self.kline_history) > max_needed:
                self.kline_history = self.kline_history[-max_needed:]
            
            # 计算RSI
            current_rsi = self.calculate_rsi(self.kline_history)
            
            # 更新RSI历史
            self.rsi_history.append(current_rsi)
            if len(self.rsi_history) > max_needed:
                self.rsi_history = self.rsi_history[-max_needed:]
            
            return current_rsi
        
        except Exception as e:
            self.logger.error(f"RSI计算错误: {e}")
            # 出错时返回中性值
            return 50.0
    
    def check_rsi_level(self, rsi_value: float) -> Tuple[RsiLevel, RsiLevel]:
        """
        检查RSI值所处的分层级别
        
        Args:
            rsi_value: RSI值
            
        Returns:
            Tuple[RsiLevel, RsiLevel]: (多头级别, 空头级别)
        """
        # 检查多头级别
        long_level = RsiLevel.NONE
        if rsi_value <= self.long_levels[0]:
            long_level = RsiLevel.LEVEL1
            if rsi_value <= self.long_levels[1]:
                long_level = RsiLevel.LEVEL2
                if rsi_value <= self.long_levels[2]:
                    long_level = RsiLevel.LEVEL3
        
        # 检查空头级别
        short_level = RsiLevel.NONE
        if rsi_value >= self.short_levels[0]:
            short_level = RsiLevel.LEVEL1
            if rsi_value >= self.short_levels[1]:
                short_level = RsiLevel.LEVEL2
                if rsi_value >= self.short_levels[2]:
                    short_level = RsiLevel.LEVEL3
        
        return long_level, short_level
    
    def update_extreme_values(self, rsi_value: float, timestamp: datetime, long_level: RsiLevel, short_level: RsiLevel) -> None:
        """
        更新RSI极值
        
        Args:
            rsi_value: 当前RSI值
            timestamp: 当前时间戳
            long_level: 当前多头级别
            short_level: 当前空头级别
        """
        # 更新多头极值
        if long_level != RsiLevel.NONE:
            if not self.long_monitoring:
                # 首次进入多头监控区域
                self.long_monitoring = True
                self.long_extreme_value = rsi_value
                self.long_extreme_time = timestamp
                self.long_level = long_level
                self.logger.info(f"开始多头极值追踪: RSI={rsi_value:.2f}, 级别={long_level.name}")
            else:
                # 已在监控区域，更新极值
                if rsi_value < self.long_extreme_value:
                    old_value = self.long_extreme_value
                    self.long_extreme_value = rsi_value
                    self.long_extreme_time = timestamp
                    self.long_level = max(self.long_level, long_level)  # 保留最高级别
                    self.logger.debug(f"更新多头极值: {old_value:.2f} -> {rsi_value:.2f}, 级别={self.long_level.name}")
        elif self.long_monitoring:
            # RSI值已离开多头区域，但仍保持监控状态
            self.logger.debug(f"RSI离开多头区域但继续监控: RSI={rsi_value:.2f}, 极值={self.long_extreme_value:.2f}")
        
        # 更新空头极值
        if short_level != RsiLevel.NONE:
            if not self.short_monitoring:
                # 首次进入空头监控区域
                self.short_monitoring = True
                self.short_extreme_value = rsi_value
                self.short_extreme_time = timestamp
                self.short_level = short_level
                self.logger.info(f"开始空头极值追踪: RSI={rsi_value:.2f}, 级别={short_level.name}")
            else:
                # 已在监控区域，更新极值
                if rsi_value > self.short_extreme_value:
                    old_value = self.short_extreme_value
                    self.short_extreme_value = rsi_value
                    self.short_extreme_time = timestamp
                    self.short_level = max(self.short_level, short_level)  # 保留最高级别
                    self.logger.debug(f"更新空头极值: {old_value:.2f} -> {rsi_value:.2f}, 级别={self.short_level.name}")
        elif self.short_monitoring:
            # RSI值已离开空头区域，但仍保持监控状态
            self.logger.debug(f"RSI离开空头区域但继续监控: RSI={rsi_value:.2f}, 极值={self.short_extreme_value:.2f}")
    
    def check_retracement(self, rsi_value: float) -> Tuple[bool, bool]:
        """
        检查RSI值是否从极值发生了足够的回撤
        
        Args:
            rsi_value: 当前RSI值
            
        Returns:
            Tuple[bool, bool]: (多头回撤信号, 空头回撤信号)
        """
        long_signal = False
        short_signal = False
        
        # 检查多头回撤
        if self.long_monitoring and self.long_extreme_value is not None:
            retracement = rsi_value - self.long_extreme_value
            if retracement >= self.retracement_points:
                self.logger.info(f"检测到多头回撤信号: 极值={self.long_extreme_value:.2f}, 当前={rsi_value:.2f}, 回撤={retracement:.2f}点")
                long_signal = True
        
        # 检查空头回撤
        if self.short_monitoring and self.short_extreme_value is not None:
            retracement = self.short_extreme_value - rsi_value
            if retracement >= self.retracement_points:
                self.logger.info(f"检测到空头回撤信号: 极值={self.short_extreme_value:.2f}, 当前={rsi_value:.2f}, 回撤={retracement:.2f}点")
                short_signal = True
        
        return long_signal, short_signal
    
    def reset_monitoring(self, reset_long: bool = False, reset_short: bool = False) -> None:
        """
        重置监控状态
        
        Args:
            reset_long: 是否重置多头监控
            reset_short: 是否重置空头监控
        """
        if reset_long:
            self.long_monitoring = False
            self.long_extreme_value = None
            self.long_extreme_time = None
            self.long_level = RsiLevel.NONE
            self.logger.debug("重置多头监控状态")
        
        if reset_short:
            self.short_monitoring = False
            self.short_extreme_value = None
            self.short_extreme_time = None
            self.short_level = RsiLevel.NONE
            self.logger.debug("重置空头监控状态")
    
    def process_kline(self, kline: Dict[str, Any]) -> Optional[SignalType]:
        """
        处理K线数据，生成交易信号
        
        Args:
            kline: K线数据，包含open, high, low, close, volume, timestamp等字段
            
        Returns:
            Optional[SignalType]: 交易信号，如果没有信号则返回None
        """
        if not self.is_active:
            return None
        
        try:
            # 计算当前RSI值
            current_rsi = self.update_rsi_history(kline)
            timestamp = datetime.fromtimestamp(kline['timestamp'] / 1000)  # 假设时间戳是毫秒级的
            
            self.logger.debug(f"处理K线: 时间={timestamp}, 收盘价={kline['close']}, RSI={current_rsi:.2f}")
            
            # 检查RSI所处级别
            long_level, short_level = self.check_rsi_level(current_rsi)
            
            # 更新极值
            self.update_extreme_values(current_rsi, timestamp, long_level, short_level)
            
            # 根据当前策略模式处理
            if self.current_mode == StrategyMode.MONITORING:
                return self._process_monitoring_mode(current_rsi, kline)
            elif self.current_mode == StrategyMode.LONG:
                return self._process_long_mode(current_rsi, kline)
            elif self.current_mode == StrategyMode.SHORT:
                return self._process_short_mode(current_rsi, kline)
            elif self.current_mode == StrategyMode.COOLING:
                return self._process_cooling_mode(current_rsi, kline)
            
            return None
            
        except Exception as e:
            self.logger.error(f"处理K线出错: {e}", exc_info=True)
            return None
    
    def _process_monitoring_mode(self, current_rsi: float, kline: Dict[str, Any]) -> Optional[SignalType]:
        """
        处理监控模式下的K线数据
        
        Args:
            current_rsi: 当前RSI值
            kline: K线数据
            
        Returns:
            Optional[SignalType]: 交易信号
        """
        # 检查是否有回撤信号
        long_signal, short_signal = self.check_retracement(current_rsi)
        
        # 优先处理多头信号
        if long_signal:
            self.logger.info(f"监控模式下触发多头开仓信号: RSI={current_rsi:.2f}, 极值={self.long_extreme_value:.2f}, 级别={self.long_level.name}")
            self.set_mode(StrategyMode.LONG)
            self.last_signal_time = datetime.now()
            self.reset_monitoring(reset_long=True)
            return SignalType.LONG_OPEN
        
        # 其次处理空头信号
        if short_signal:
            self.logger.info(f"监控模式下触发空头开仓信号: RSI={current_rsi:.2f}, 极值={self.short_extreme_value:.2f}, 级别={self.short_level.name}")
            self.set_mode(StrategyMode.SHORT)
            self.last_signal_time = datetime.now()
            self.reset_monitoring(reset_short=True)
            return SignalType.SHORT_OPEN
        
        return None
    
    def _process_long_mode(self, current_rsi: float, kline: Dict[str, Any]) -> Optional[SignalType]:
        """
        处理多头持仓模式下的K线数据
        
        Args:
            current_rsi: 当前RSI值
            kline: K线数据
            
        Returns:
            Optional[SignalType]: 交易信号
        """
        # 检查是否有空头回撤信号（可能触发反手）
        _, short_signal = self.check_retracement(current_rsi)
        
        # 检查是否达到最大持仓时间
        position_info = {"holding_periods": 0}  # 这里应该从数据库获取实际持仓信息
        
        # 如果达到最大持仓时间且有反向信号，触发反手交易
        if position_info["holding_periods"] >= self.max_holding_candles and short_signal:
            self.logger.info(f"多头持仓超时且检测到空头信号，触发反手交易: 持仓K线数={position_info['holding_periods']}, RSI={current_rsi:.2f}")
            self.set_mode(StrategyMode.SHORT)
            self.last_signal_time = datetime.now()
            self.reset_monitoring(reset_short=True)
            return SignalType.REVERSE_TRADE
        
        # 检查是否应该止盈
        if self.should_take_profit(position_info, kline):
            self.logger.info(f"多头持仓触发止盈信号: RSI={current_rsi:.2f}")
            self.set_mode(StrategyMode.COOLING)
            self.cooling_count = 0
            return SignalType.TAKE_PROFIT
        
        # 检查是否应该止损
        if self.should_stop_loss(position_info, kline):
            self.logger.info(f"多头持仓触发止损信号: RSI={current_rsi:.2f}")
            self.set_mode(StrategyMode.COOLING)
            self.cooling_count = 0
            return SignalType.STOP_LOSS
        
        # 检查是否应该加仓
        if self.should_add_position(position_info, kline):
            self.logger.info(f"多头持仓触发加仓信号: RSI={current_rsi:.2f}, 已加仓次数={position_info.get('additional_positions_count', 0)}")
            return SignalType.LONG_ADD
        
        # 检查是否达到最大持仓时间
        if position_info["holding_periods"] >= self.max_holding_candles:
            self.logger.info(f"多头持仓达到最大持仓时间，触发平仓: 持仓K线数={position_info['holding_periods']}")
            self.set_mode(StrategyMode.COOLING)
            self.cooling_count = 0
            return SignalType.TIMEOUT_CLOSE
        
        return None
    
    def _process_short_mode(self, current_rsi: float, kline: Dict[str, Any]) -> Optional[SignalType]:
        """
        处理空头持仓模式下的K线数据
        
        Args:
            current_rsi: 当前RSI值
            kline: K线数据
            
        Returns:
            Optional[SignalType]: 交易信号
        """
        # 检查是否有多头回撤信号（可能触发反手）
        long_signal, _ = self.check_retracement(current_rsi)
        
        # 检查是否达到最大持仓时间
        position_info = {"holding_periods": 0}  # 这里应该从数据库获取实际持仓信息
        
        # 如果达到最大持仓时间且有反向信号，触发反手交易
        if position_info["holding_periods"] >= self.max_holding_candles and long_signal:
            self.logger.info(f"空头持仓超时且检测到多头信号，触发反手交易: 持仓K线数={position_info['holding_periods']}, RSI={current_rsi:.2f}")
            self.set_mode(StrategyMode.LONG)
            self.last_signal_time = datetime.now()
            self.reset_monitoring(reset_long=True)
            return SignalType.REVERSE_TRADE
        
        # 检查是否应该止盈
        if self.should_take_profit(position_info, kline):
            self.logger.info(f"空头持仓触发止盈信号: RSI={current_rsi:.2f}")
            self.set_mode(StrategyMode.COOLING)
            self.cooling_count = 0
            return SignalType.TAKE_PROFIT
        
        # 检查是否应该止损
        if self.should_stop_loss(position_info, kline):
            self.logger.info(f"空头持仓触发止损信号: RSI={current_rsi:.2f}")
            self.set_mode(StrategyMode.COOLING)
            self.cooling_count = 0
            return SignalType.STOP_LOSS
        
        # 检查是否应该加仓
        if self.should_add_position(position_info, kline):
            self.logger.info(f"空头持仓触发加仓信号: RSI={current_rsi:.2f}, 已加仓次数={position_info.get('additional_positions_count', 0)}")
            return SignalType.SHORT_ADD
        
        # 检查是否达到最大持仓时间
        if position_info["holding_periods"] >= self.max_holding_candles:
            self.logger.info(f"空头持仓达到最大持仓时间，触发平仓: 持仓K线数={position_info['holding_periods']}")
            self.set_mode(StrategyMode.COOLING)
            self.cooling_count = 0
            return SignalType.TIMEOUT_CLOSE
        
        return None
    
    def _process_cooling_mode(self, current_rsi: float, kline: Dict[str, Any]) -> Optional[SignalType]:
        """
        处理冷却模式下的K线数据
        
        Args:
            current_rsi: 当前RSI值
            kline: K线数据
            
        Returns:
            Optional[SignalType]: 交易信号
        """
        # 增加冷却计数
        self.cooling_count += 1
        
        # 检查是否冷却结束
        if self.cooling_count >= self.cooling_candles:
            self.logger.info(f"冷却期结束，恢复监控模式: 冷却K线数={self.cooling_count}")
            self.set_mode(StrategyMode.MONITORING)
            # 不重置极值监控，保持对之前极值的追踪
        else:
            self.logger.debug(f"冷却中: {self.cooling_count}/{self.cooling_candles}")
        
        return None
    
    def calculate_position_size(self, account_balance: float, current_price: float) -> float:
        """
        计算持仓大小
        
        Args:
            account_balance: 账户余额
            current_price: 当前价格
            
        Returns:
            float: 建议的持仓大小（合约数量）
        """
        try:
            # 获取账户配置
            order_fund_ratio = settings.ORDER_FUND_RATIO
            leverage = settings.DEFAULT_LEVERAGE
            
            # 计算可用于此次交易的资金
            available_funds = account_balance * order_fund_ratio
            
            # 计算合约数量
            # 对于ETH合约，通常是按照ETH的数量来计算的
            position_size = (available_funds * leverage) / current_price
            
            # 根据交易所规则进行数量精度调整
            # 这里假设ETH合约最小精度为0.001
            position_size = round(position_size, 3)
            
            self.logger.info(f"计算持仓大小: 账户余额={account_balance:.2f}, 价格={current_price:.2f}, 杠杆={leverage}倍, 资金比例={order_fund_ratio:.2f}, 持仓大小={position_size:.3f}")
            
            return position_size
            
        except Exception as e:
            self.logger.error(f"计算持仓大小出错: {e}")
            return 0.0
    
    def should_add_position(self, position: Dict[str, Any], kline: Dict[str, Any]) -> bool:
        """
        判断是否应该加仓
        
        Args:
            position: 当前持仓信息
            kline: 当前K线数据
            
        Returns:
            bool: 是否应该加仓
        """
        try:
            # 获取当前RSI值
            current_rsi = self.rsi_history[-1] if self.rsi_history else 50.0
            
            # 获取已加仓次数
            additional_positions_count = position.get("additional_positions_count", 0)
            
            # 如果已达到最大加仓次数，不再加仓
            if additional_positions_count >= self.max_additional_positions:
                return False
            
            # 根据持仓方向判断是否有回撤信号
            if self.current_mode == StrategyMode.LONG:
                # 检查是否有多头回撤信号
                long_signal, _ = self.check_retracement(current_rsi)
                if long_signal:
                    self.logger.info(f"多头持仓检测到加仓信号: RSI={current_rsi:.2f}, 已加仓次数={additional_positions_count}")
                    # 重置多头极值监控，为下一次加仓做准备
                    self.reset_monitoring(reset_long=True)
                    return True
            
            elif self.current_mode == StrategyMode.SHORT:
                # 检查是否有空头回撤信号
                _, short_signal = self.check_retracement(current_rsi)
                if short_signal:
                    self.logger.info(f"空头持仓检测到加仓信号: RSI={current_rsi:.2f}, 已加仓次数={additional_positions_count}")
                    # 重置空头极值监控，为下一次加仓做准备
                    self.reset_monitoring(reset_short=True)
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"判断加仓出错: {e}")
            return False
    
    def should_take_profit(self, position: Dict[str, Any], kline: Dict[str, Any]) -> bool:
        """
        判断是否应该止盈
        
        Args:
            position: 当前持仓信息
            kline: 当前K线数据
            
        Returns:
            bool: 是否应该止盈
        """
        try:
            # 获取持仓信息
            holding_periods = position.get("holding_periods", 0)
            max_profit = position.get("max_profit", 0)
            current_profit = position.get("unrealized_pnl", 0)
            
            # 如果没有盈利，不触发止盈
            if current_profit <= 0:
                return False
            
            # 更新最大浮盈
            if current_profit > max_profit:
                max_profit = current_profit
                # 这里应该更新数据库中的max_profit
            
            # 计算回撤
            profit_retracement = max_profit - current_profit
            
            # 检查分层止盈条件
            for window, retracement_points, min_profit in self.profit_taking_config:
                # 如果持仓时间达到窗口要求
                if holding_periods >= window:
                    # 如果回撤达到阈值且当前盈利仍然大于最小盈利要求
                    if profit_retracement >= retracement_points and current_profit >= min_profit:
                        self.logger.info(
                            f"触发分层浮动止盈: 持仓K线数={holding_periods}, 窗口={window}, "
                            f"最大浮盈={max_profit:.2f}, 当前盈利={current_profit:.2f}, "
                            f"回撤={profit_retracement:.2f}点, 阈值={retracement_points}点, "
                            f"最小盈利要求={min_profit}点"
                        )
                        return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"判断止盈出错: {e}")
            return False
    
    def should_stop_loss(self, position: Dict[str, Any], kline: Dict[str, Any]) -> bool:
        """
        判断是否应该止损
        
        Args:
            position: 当前持仓信息
            kline: 当前K线数据
            
        Returns:
            bool: 是否应该止损
        """
        try:
            # 获取当前亏损
            current_loss = position.get("unrealized_pnl", 0)
            
            # 如果亏损达到固定止损点数，触发止损
            if current_loss <= -self.fixed_stop_loss_points:
                self.logger.info(f"触发固定止损: 当前亏损={current_loss:.2f}点, 止损阈值={self.fixed_stop_loss_points}点")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"判断止损出错: {e}")
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        """
        将策略状态转换为字典
        
        Returns:
            Dict[str, Any]: 策略状态字典
        """
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "symbol": self.symbol,
            "account_ids": self.account_ids,
            "is_active": self.is_active,
            "rsi_period": self.rsi_period,
            "long_levels": self.long_levels,
            "short_levels": self.short_levels,
            "retracement_points": self.retracement_points,
            "max_additional_positions": self.max_additional_positions,
            "fixed_stop_loss_points": self.fixed_stop_loss_points,
            "profit_taking_config": self.profit_taking_config,
            "max_holding_candles": self.max_holding_candles,
            "cooling_candles": self.cooling_candles,
            "current_mode": self.current_mode.value,
            "cooling_count": self.cooling_count,
            "long_monitoring": self.long_monitoring,
            "long_extreme_value": float(self.long_extreme_value) if self.long_extreme_value is not None else None,
            "long_extreme_time": self.long_extreme_time.isoformat() if self.long_extreme_time else None,
            "long_level": self.long_level.value,
            "short_monitoring": self.short_monitoring,
            "short_extreme_value": float(self.short_extreme_value) if self.short_extreme_value is not None else None,
            "short_extreme_time": self.short_extreme_time.isoformat() if self.short_extreme_time else None,
            "short_level": self.short_level.value,
            "last_signal_time": self.last_signal_time.isoformat() if self.last_signal_time else None,
            "last_trade_time": self.last_trade_time.isoformat() if self.last_trade_time else None,
        }
    
    def from_dict(self, data: Dict[str, Any]) -> None:
        """
        从字典加载策略状态
        
        Args:
            data: 策略状态字典
        """
        try:
            # 基本属性
            self.strategy_id = data.get("strategy_id", self.strategy_id)
            self.name = data.get("name", self.name)
            self.symbol = data.get("symbol", self.symbol)
            self.account_ids = data.get("account_ids", self.account_ids)
            self.is_active = data.get("is_active", self.is_active)
            
            # 策略参数
            self.rsi_period = data.get("rsi_period", self.rsi_period)
            self.long_levels = data.get("long_levels", self.long_levels)
            self.short_levels = data.get("short_levels", self.short_levels)
            self.retracement_points = data.get("retracement_points", self.retracement_points)
            self.max_additional_positions = data.get("max_additional_positions", self.max_additional_positions)
            self.fixed_stop_loss_points = data.get("fixed_stop_loss_points", self.fixed_stop_loss_points)
            self.profit_taking_config = data.get("profit_taking_config", self.profit_taking_config)
            self.max_holding_candles = data.get("max_holding_candles", self.max_holding_candles)
            self.cooling_candles = data.get("cooling_candles", self.cooling_candles)
            
            # 运行时状态
            mode_str = data.get("current_mode")
            if mode_str:
                self.current_mode = StrategyMode(mode_str)
            self.cooling_count = data.get("cooling_count", self.cooling_count)
            
            # 多头监控状态
            self.long_monitoring = data.get("long_monitoring", self.long_monitoring)
            self.long_extreme_value = data.get("long_extreme_value", self.long_extreme_value)
            
            long_extreme_time = data.get("long_extreme_time")
            if long_extreme_time:
                self.long_extreme_time = datetime.fromisoformat(long_extreme_time)
            
            long_level = data.get("long_level")
            if long_level is not None:
                self.long_level = RsiLevel(long_level)
            
            # 空头监控状态
            self.short_monitoring = data.get("short_monitoring", self.short_monitoring)
            self.short_extreme_value = data.get("short_extreme_value", self.short_extreme_value)
            
            short_extreme_time = data.get("short_extreme_time")
            if short_extreme_time:
                self.short_extreme_time = datetime.fromisoformat(short_extreme_time)
            
            short_level = data.get("short_level")
            if short_level is not None:
                self.short_level = RsiLevel(short_level)
            
            # 时间戳
            last_signal_time = data.get("last_signal_time")
            if last_signal_time:
                self.last_signal_time = datetime.fromisoformat(last_signal_time)
            
            last_trade_time = data.get("last_trade_time")
            if last_trade_time:
                self.last_trade_time = datetime.fromisoformat(last_trade_time)
            
            self.logger.info(f"从字典加载策略状态: {self.strategy_id}")
            
        except Exception as e:
            self.logger.error(f"从字典加载策略状态出错: {e}", exc_info=True)
