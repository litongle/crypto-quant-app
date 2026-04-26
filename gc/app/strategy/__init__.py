"""
RSI分层极值追踪自动量化交易系统 - 策略模块

该模块包含交易策略的核心实现，包括：
- 策略基类(BaseStrategy)：所有策略的抽象基类
- 策略枚举(StrategyType)：支持的策略类型
- RSI分层极值追踪策略(RsiLayeredStrategy)：核心交易策略实现
"""

from enum import Enum
from typing import Dict, List, Any, Optional, Union, Tuple
from abc import ABC, abstractmethod
import logging
from datetime import datetime, timedelta

from app.core.config import settings


# 配置日志
logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """策略类型枚举"""
    RSI_LAYERED = "rsi_layered"  # RSI分层极值追踪策略
    # 未来可能添加的其他策略类型
    # MACD_CROSS = "macd_cross"  # MACD交叉策略
    # BOLLINGER_BANDS = "bollinger_bands"  # 布林带策略


class SignalType(Enum):
    """交易信号类型枚举"""
    LONG_OPEN = "long_open"          # 多头开仓信号
    LONG_ADD = "long_add"            # 多头加仓信号
    LONG_CLOSE = "long_close"        # 多头平仓信号
    SHORT_OPEN = "short_open"        # 空头开仓信号
    SHORT_ADD = "short_add"          # 空头加仓信号
    SHORT_CLOSE = "short_close"      # 空头平仓信号
    STOP_LOSS = "stop_loss"          # 止损信号
    TAKE_PROFIT = "take_profit"      # 止盈信号
    TIMEOUT_CLOSE = "timeout_close"  # 超时平仓信号
    REVERSE_TRADE = "reverse_trade"  # 反向交易信号


class StrategyMode(Enum):
    """策略运行模式枚举"""
    MONITORING = "monitoring"  # 监控模式，等待信号
    LONG = "long"              # 多头持仓模式
    SHORT = "short"            # 空头持仓模式
    COOLING = "cooling"        # 冷却模式，等待冷却期结束


class BaseStrategy(ABC):
    """
    策略基类
    
    所有具体策略实现都应继承此类，并实现必要的抽象方法
    """
    
    def __init__(self, strategy_id: str, name: str, symbol: str, account_ids: List[int]):
        """
        初始化策略基类
        
        Args:
            strategy_id: 策略ID
            name: 策略名称
            symbol: 交易对
            account_ids: 关联账户ID列表
        """
        self.strategy_id = strategy_id
        self.name = name
        self.symbol = symbol
        self.account_ids = account_ids
        self.is_active = True
        self.current_mode = StrategyMode.MONITORING
        self.last_signal_time = None
        self.last_trade_time = None
        self.logger = logging.getLogger(f"strategy.{strategy_id}")
    
    @abstractmethod
    def process_kline(self, kline: Dict[str, Any]) -> Optional[SignalType]:
        """
        处理K线数据，生成交易信号
        
        Args:
            kline: K线数据
            
        Returns:
            Optional[SignalType]: 交易信号，如果没有信号则返回None
        """
        pass
    
    @abstractmethod
    def calculate_position_size(self, account_balance: float, current_price: float) -> float:
        """
        计算持仓大小
        
        Args:
            account_balance: 账户余额
            current_price: 当前价格
            
        Returns:
            float: 建议的持仓大小
        """
        pass
    
    @abstractmethod
    def should_add_position(self, position: Dict[str, Any], kline: Dict[str, Any]) -> bool:
        """
        判断是否应该加仓
        
        Args:
            position: 当前持仓信息
            kline: 当前K线数据
            
        Returns:
            bool: 是否应该加仓
        """
        pass
    
    @abstractmethod
    def should_take_profit(self, position: Dict[str, Any], kline: Dict[str, Any]) -> bool:
        """
        判断是否应该止盈
        
        Args:
            position: 当前持仓信息
            kline: 当前K线数据
            
        Returns:
            bool: 是否应该止盈
        """
        pass
    
    @abstractmethod
    def should_stop_loss(self, position: Dict[str, Any], kline: Dict[str, Any]) -> bool:
        """
        判断是否应该止损
        
        Args:
            position: 当前持仓信息
            kline: 当前K线数据
            
        Returns:
            bool: 是否应该止损
        """
        pass
    
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """
        将策略状态转换为字典
        
        Returns:
            Dict[str, Any]: 策略状态字典
        """
        pass
    
    @abstractmethod
    def from_dict(self, data: Dict[str, Any]) -> None:
        """
        从字典加载策略状态
        
        Args:
            data: 策略状态字典
        """
        pass
    
    def activate(self) -> None:
        """激活策略"""
        self.is_active = True
        self.logger.info(f"Strategy {self.strategy_id} activated")
    
    def deactivate(self) -> None:
        """停用策略"""
        self.is_active = False
        self.logger.info(f"Strategy {self.strategy_id} deactivated")
    
    def set_mode(self, mode: StrategyMode) -> None:
        """
        设置策略模式
        
        Args:
            mode: 新的策略模式
        """
        self.logger.info(f"Strategy {self.strategy_id} mode changed: {self.current_mode.value} -> {mode.value}")
        self.current_mode = mode


# 导出所有需要的组件
__all__ = [
    "StrategyType", 
    "SignalType", 
    "StrategyMode", 
    "BaseStrategy"
]
