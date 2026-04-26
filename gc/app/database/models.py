"""
RSI分层极值追踪自动量化交易系统 - 数据库模型定义

定义所有数据库表的ORM模型，包括：
- K线数据表(Kline) - 使用TimescaleDB超表存储1分钟K线
- 交易账户表(TradingAccount) - 存储交易所账户信息
- 持仓记录表(Position) - 存储当前持仓信息
- 交易记录表(Trade) - 存储历史交易记录
- 策略状态表(StrategyState) - 存储策略运行状态
- 系统配置表(SystemConfig) - 存储系统运行时配置
- 告警记录表(Alert) - 存储系统告警信息
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
import enum
import json
import uuid

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, 
    Text, ForeignKey, UniqueConstraint, Index, JSON, 
    Enum, func, text, TIMESTAMP, BigInteger, Numeric
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.mutable import MutableDict

from app.database import Base
from app.core.config import settings


class ExchangeType(enum.Enum):
    """交易所类型枚举"""
    OKX = "okx"
    BINANCE = "binance"
    HTX = "htx"


class OrderType(enum.Enum):
    """订单类型枚举"""
    MARKET = "market"  # 市价单
    LIMIT = "limit"    # 限价单


class OrderSide(enum.Enum):
    """订单方向枚举"""
    BUY = "buy"        # 买入/做多
    SELL = "sell"      # 卖出/做空


class PositionSide(enum.Enum):
    """持仓方向枚举"""
    LONG = "long"      # 多头持仓
    SHORT = "short"    # 空头持仓


class OrderStatus(enum.Enum):
    """订单状态枚举"""
    PENDING = "pending"        # 待处理
    SUBMITTED = "submitted"    # 已提交
    PARTIAL = "partial"        # 部分成交
    FILLED = "filled"          # 完全成交
    CANCELED = "canceled"      # 已取消
    REJECTED = "rejected"      # 被拒绝
    EXPIRED = "expired"        # 已过期


class AlertLevel(enum.Enum):
    """告警级别枚举"""
    INFO = "info"          # 信息
    WARNING = "warning"    # 警告
    ERROR = "error"        # 错误
    CRITICAL = "critical"  # 严重


class AlertType(enum.Enum):
    """告警类型枚举"""
    SYSTEM = "system"          # 系统告警
    ACCOUNT = "account"        # 账户告警
    TRADE = "trade"            # 交易告警
    STRATEGY = "strategy"      # 策略告警
    API = "api"                # API告警
    SECURITY = "security"      # 安全告警


class Kline(Base):
    """
    K线数据表 - 使用TimescaleDB超表存储1分钟K线数据
    
    注意：此表将被转换为TimescaleDB超表，以优化时间序列数据的存储和查询
    """
    __tablename__ = "klines"
    
    # 主键 - 使用时间戳和交易对作为联合主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 时间戳 - 精确到毫秒
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    
    # 交易所和交易对
    exchange = Column(Enum(ExchangeType), nullable=False)
    symbol = Column(String(30), nullable=False, index=True)
    
    # K线周期(例如: 1m, 5m, 15m, 1h, 4h, 1d)
    interval = Column(String(10), nullable=False, default="1m")
    
    # OHLCV数据
    open = Column(Numeric(20, 8), nullable=False)
    high = Column(Numeric(20, 8), nullable=False)
    low = Column(Numeric(20, 8), nullable=False)
    close = Column(Numeric(20, 8), nullable=False)
    volume = Column(Numeric(30, 8), nullable=False)
    
    # 额外的交易数据
    quote_volume = Column(Numeric(30, 8), nullable=True)  # 报价货币成交量
    trades_count = Column(Integer, nullable=True)         # 成交笔数
    taker_buy_volume = Column(Numeric(30, 8), nullable=True)  # 主动买入成交量
    taker_buy_quote_volume = Column(Numeric(30, 8), nullable=True)  # 主动买入成交额
    
    # 技术指标数据 - 预计算以提高查询性能
    rsi_14 = Column(Numeric(10, 4), nullable=True)  # RSI(14)值
    
    # 创建联合索引以加速查询
    __table_args__ = (
        # 联合唯一约束，确保每个交易所-交易对-时间戳-周期的组合是唯一的
        UniqueConstraint('exchange', 'symbol', 'timestamp', 'interval', name='uq_kline_exchange_symbol_timestamp_interval'),
        
        # 创建用于范围查询的复合索引
        Index('ix_klines_exchange_symbol_interval_timestamp', 'exchange', 'symbol', 'interval', 'timestamp'),
        
        # 为RSI查询创建索引
        Index('ix_klines_rsi_14', 'rsi_14'),
        
        # 表注释
        {'comment': 'K线数据表，存储各交易所1分钟K线数据'}
    )
    
    @classmethod
    def create_hypertable(cls, conn):
        """创建TimescaleDB超表"""
        # 检查是否已经是超表
        check_sql = """
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_name = 'klines';
        """
        result = conn.execute(text(check_sql))
        if result.scalar() is None:
            # 如果不是超表，则创建
            create_sql = """
            SELECT create_hypertable('klines', 'timestamp', 
                                    chunk_time_interval => INTERVAL '1 day',
                                    if_not_exists => TRUE);
            """
            conn.execute(text(create_sql))
            
            # 创建压缩策略
            compress_sql = """
            ALTER TABLE klines SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'exchange,symbol,interval'
            );
            """
            conn.execute(text(compress_sql))
            
            # 设置压缩策略，7天后的数据自动压缩
            compression_policy_sql = """
            SELECT add_compression_policy('klines', INTERVAL '7 days');
            """
            conn.execute(text(compression_policy_sql))
            
            # 设置数据保留策略，只保留设定天数的数据
            retention_policy_sql = f"""
            SELECT add_retention_policy('klines', INTERVAL '{settings.DATA_RETENTION_DAYS} days');
            """
            conn.execute(text(retention_policy_sql))
            
            print(f"TimescaleDB hypertable created for klines with {settings.DATA_RETENTION_DAYS} days retention")


class TradingAccount(Base):
    """
    交易账户表 - 存储交易所账户信息
    
    包含API密钥等敏感信息(加密存储)和账户余额信息
    """
    __tablename__ = "trading_accounts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 账户标识信息
    name = Column(String(100), nullable=False, comment="账户名称")
    exchange = Column(Enum(ExchangeType), nullable=False, comment="交易所")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否激活")
    
    # API密钥信息 - 加密存储
    api_key = Column(String(255), nullable=False, comment="API Key(加密)")
    api_secret = Column(String(255), nullable=False, comment="API Secret(加密)")
    passphrase = Column(String(255), nullable=True, comment="API密码短语(加密，部分交易所需要)")
    
    # 账户配置
    leverage = Column(Integer, default=20, nullable=False, comment="杠杆倍数")
    max_position_value = Column(Float, default=0.8, nullable=False, comment="最大持仓价值占比")
    order_fund_ratio = Column(Float, default=0.25, nullable=False, comment="单次开仓资金比例")
    
    # 账户余额信息 - 定期更新
    total_equity_usdt = Column(Numeric(20, 8), default=0, comment="总权益(USDT)")
    available_balance_usdt = Column(Numeric(20, 8), default=0, comment="可用余额(USDT)")
    margin_balance_usdt = Column(Numeric(20, 8), default=0, comment="保证金余额(USDT)")
    unrealized_pnl_usdt = Column(Numeric(20, 8), default=0, comment="未实现盈亏(USDT)")
    
    # 账户状态
    last_update_time = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="最后更新时间")
    last_sync_time = Column(DateTime, nullable=True, comment="最后同步时间")
    error_message = Column(String(500), nullable=True, comment="最近错误信息")
    
    # 额外配置 - 使用JSONB存储可能的自定义配置
    extra_config = Column(JSONB, default={}, comment="额外配置")
    
    # 关联关系
    positions = relationship("Position", back_populates="account", cascade="all, delete-orphan")
    trades = relationship("Trade", back_populates="account", cascade="all, delete-orphan")
    
    __table_args__ = (
        # 确保账户名称在同一交易所内唯一
        UniqueConstraint('name', 'exchange', name='uq_account_name_exchange'),
        
        # 索引
        Index('ix_trading_accounts_exchange', 'exchange'),
        Index('ix_trading_accounts_is_active', 'is_active'),
        
        {'comment': '交易账户表，存储交易所API密钥和账户信息'}
    )
    
    @hybrid_property
    def risk_level(self):
        """计算账户风险等级"""
        if self.total_equity_usdt <= 0:
            return 1.0  # 避免除以零
        
        # 计算已用保证金占总权益的比例
        margin_ratio = (self.margin_balance_usdt - self.available_balance_usdt) / self.total_equity_usdt
        return min(margin_ratio, 1.0)  # 返回0-1之间的值


class Position(Base):
    """
    持仓记录表 - 存储当前持仓信息
    """
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 关联账户
    account_id = Column(Integer, ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False)
    account = relationship("TradingAccount", back_populates="positions")
    
    # 持仓基本信息
    symbol = Column(String(30), nullable=False, comment="交易对")
    side = Column(Enum(PositionSide), nullable=False, comment="持仓方向")
    size = Column(Numeric(20, 8), nullable=False, comment="持仓数量")
    leverage = Column(Integer, nullable=False, comment="杠杆倍数")
    
    # 价格信息
    entry_price = Column(Numeric(20, 8), nullable=False, comment="开仓均价")
    mark_price = Column(Numeric(20, 8), nullable=False, comment="标记价格")
    liquidation_price = Column(Numeric(20, 8), nullable=True, comment="强平价格")
    
    # 盈亏信息
    unrealized_pnl = Column(Numeric(20, 8), default=0, comment="未实现盈亏")
    realized_pnl = Column(Numeric(20, 8), default=0, comment="已实现盈亏")
    
    # 保证金信息
    margin_mode = Column(String(20), default="cross", comment="保证金模式(cross:全仓, isolated:逐仓)")
    initial_margin = Column(Numeric(20, 8), comment="初始保证金")
    position_margin = Column(Numeric(20, 8), comment="持仓保证金")
    
    # 策略跟踪信息
    strategy_id = Column(String(50), nullable=True, comment="策略ID")
    open_time = Column(DateTime, default=datetime.utcnow, comment="开仓时间")
    holding_periods = Column(Integer, default=0, comment="持仓K线数")
    avg_cost = Column(Numeric(20, 8), nullable=True, comment="平均成本")
    
    # RSI策略特定字段
    rsi_extreme_value = Column(Numeric(10, 4), nullable=True, comment="RSI极值")
    additional_positions_count = Column(Integer, default=0, comment="已加仓次数")
    max_profit = Column(Numeric(20, 8), default=0, comment="最大浮动盈利")
    stop_loss_price = Column(Numeric(20, 8), nullable=True, comment="止损价格")
    
    # 状态信息
    last_update_time = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="最后更新时间")
    notes = Column(String(500), nullable=True, comment="持仓备注")
    
    # 额外信息
    extra_data = Column(JSONB, default={}, comment="额外数据")
    
    __table_args__ = (
        # 确保每个账户的每个交易对只有一个同向持仓
        UniqueConstraint('account_id', 'symbol', 'side', name='uq_position_account_symbol_side'),
        
        # 索引
        Index('ix_positions_account_id', 'account_id'),
        Index('ix_positions_symbol', 'symbol'),
        Index('ix_positions_open_time', 'open_time'),
        Index('ix_positions_strategy_id', 'strategy_id'),
        
        {'comment': '持仓记录表，存储当前持仓信息'}
    )
    
    @hybrid_property
    def position_value(self):
        """计算持仓价值"""
        return float(self.size) * float(self.mark_price)
    
    @hybrid_property
    def profit_percentage(self):
        """计算盈亏百分比"""
        if float(self.entry_price) == 0:
            return 0
            
        if self.side == PositionSide.LONG:
            return (float(self.mark_price) - float(self.entry_price)) / float(self.entry_price) * 100
        else:
            return (float(self.entry_price) - float(self.mark_price)) / float(self.entry_price) * 100


class Trade(Base):
    """
    交易记录表 - 存储历史交易记录
    """
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 交易所订单ID
    exchange_order_id = Column(String(100), nullable=True, comment="交易所订单ID")
    exchange_trade_id = Column(String(100), nullable=True, comment="交易所成交ID")
    
    # 关联账户
    account_id = Column(Integer, ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False)
    account = relationship("TradingAccount", back_populates="trades")
    
    # 交易基本信息
    symbol = Column(String(30), nullable=False, comment="交易对")
    side = Column(Enum(OrderSide), nullable=False, comment="交易方向")
    type = Column(Enum(OrderType), nullable=False, comment="订单类型")
    
    # 价格和数量
    price = Column(Numeric(20, 8), nullable=False, comment="成交价格")
    amount = Column(Numeric(20, 8), nullable=False, comment="成交数量")
    value = Column(Numeric(20, 8), nullable=False, comment="成交价值")
    fee = Column(Numeric(20, 8), default=0, comment="手续费")
    fee_currency = Column(String(10), nullable=True, comment="手续费币种")
    
    # 策略信息
    strategy_id = Column(String(50), nullable=True, comment="策略ID")
    position_id = Column(Integer, nullable=True, comment="关联持仓ID")
    trade_type = Column(String(20), nullable=True, comment="交易类型(open:开仓, add:加仓, close:平仓, sl:止损, tp:止盈)")
    
    # RSI策略特定字段
    rsi_value = Column(Numeric(10, 4), nullable=True, comment="交易时RSI值")
    rsi_extreme = Column(Numeric(10, 4), nullable=True, comment="RSI极值")
    rsi_retracement = Column(Numeric(10, 4), nullable=True, comment="RSI回撤点数")
    holding_periods = Column(Integer, nullable=True, comment="持仓K线数")
    pnl = Column(Numeric(20, 8), nullable=True, comment="该笔交易盈亏")
    
    # 状态信息
    status = Column(Enum(OrderStatus), default=OrderStatus.FILLED, comment="订单状态")
    create_time = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    update_time = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 额外信息
    notes = Column(String(500), nullable=True, comment="交易备注")
    extra_data = Column(JSONB, default={}, comment="额外数据")
    
    __table_args__ = (
        # 索引
        Index('ix_trades_account_id', 'account_id'),
        Index('ix_trades_symbol', 'symbol'),
        Index('ix_trades_create_time', 'create_time'),
        Index('ix_trades_strategy_id', 'strategy_id'),
        Index('ix_trades_position_id', 'position_id'),
        
        # 如果有交易所订单ID，确保唯一
        Index('ix_trades_exchange_order_id', 'exchange_order_id'),
        Index('ix_trades_exchange_trade_id', 'exchange_trade_id'),
        
        {'comment': '交易记录表，存储历史交易记录'}
    )
    
    @classmethod
    def create_hypertable(cls, conn):
        """创建TimescaleDB超表"""
        # 检查是否已经是超表
        check_sql = """
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_name = 'trades';
        """
        result = conn.execute(text(check_sql))
        if result.scalar() is None:
            # 如果不是超表，则创建
            create_sql = """
            SELECT create_hypertable('trades', 'create_time', 
                                    chunk_time_interval => INTERVAL '1 day',
                                    if_not_exists => TRUE);
            """
            conn.execute(text(create_sql))
            
            # 创建压缩策略
            compress_sql = """
            ALTER TABLE trades SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'account_id,symbol,strategy_id'
            );
            """
            conn.execute(text(compress_sql))
            
            # 设置压缩策略，7天后的数据自动压缩
            compression_policy_sql = """
            SELECT add_compression_policy('trades', INTERVAL '7 days');
            """
            conn.execute(text(compression_policy_sql))
            
            # 设置数据保留策略，只保留设定天数的数据
            retention_policy_sql = f"""
            SELECT add_retention_policy('trades', INTERVAL '{settings.TRADE_LOG_RETENTION_DAYS} days');
            """
            conn.execute(text(retention_policy_sql))
            
            print(f"TimescaleDB hypertable created for trades with {settings.TRADE_LOG_RETENTION_DAYS} days retention")


class StrategyState(Base):
    """
    策略状态表 - 存储策略运行状态
    """
    __tablename__ = "strategy_states"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 策略标识
    strategy_id = Column(String(50), nullable=False, unique=True, comment="策略ID")
    name = Column(String(100), nullable=False, comment="策略名称")
    
    # 策略配置
    symbol = Column(String(30), nullable=False, comment="交易对")
    account_ids = Column(JSONB, default=[], comment="关联账户ID列表")
    is_active = Column(Boolean, default=True, comment="是否激活")
    
    # RSI策略特定状态
    rsi_period = Column(Integer, default=14, comment="RSI周期")
    long_level1 = Column(Integer, default=35, comment="多头第一层阈值")
    long_level2 = Column(Integer, default=30, comment="多头第二层阈值")
    long_level3 = Column(Integer, default=20, comment="多头第三层阈值")
    short_level1 = Column(Integer, default=65, comment="空头第一层阈值")
    short_level2 = Column(Integer, default=70, comment="空头第二层阈值")
    short_level3 = Column(Integer, default=80, comment="空头第三层阈值")
    
    # 极值回撤参数
    retracement_points = Column(Integer, default=2, comment="极值回撤触发点数")
    
    # 加仓参数
    max_additional_positions = Column(Integer, default=4, comment="最大加仓次数")
    
    # 止损参数
    fixed_stop_loss_points = Column(Integer, default=6, comment="固定止损点数")
    
    # 止盈参数（分层）- 使用JSONB存储复杂配置
    profit_taking_config = Column(JSONB, default=[], comment="止盈配置")
    
    # 持仓管理
    max_holding_candles = Column(Integer, default=60, comment="最大持仓K线数")
    cooling_candles = Column(Integer, default=3, comment="平仓后冷却期K线数")
    
    # 运行时状态
    current_mode = Column(String(20), default="monitoring", comment="当前模式(monitoring:监控中, long:多头, short:空头, cooling:冷却中)")
    cooling_count = Column(Integer, default=0, comment="冷却计数")
    last_signal_time = Column(DateTime, nullable=True, comment="最后信号时间")
    last_trade_time = Column(DateTime, nullable=True, comment="最后交易时间")
    
    # 多头监控状态
    long_monitoring = Column(Boolean, default=False, comment="是否监控多头")
    long_extreme_value = Column(Numeric(10, 4), nullable=True, comment="多头RSI极值")
    long_extreme_time = Column(DateTime, nullable=True, comment="多头极值时间")
    
    # 空头监控状态
    short_monitoring = Column(Boolean, default=False, comment="是否监控空头")
    short_extreme_value = Column(Numeric(10, 4), nullable=True, comment="空头RSI极值")
    short_extreme_time = Column(DateTime, nullable=True, comment="空头极值时间")
    
    # 状态信息
    create_time = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    update_time = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    last_error = Column(String(500), nullable=True, comment="最后错误信息")
    
    # 额外配置和状态
    extra_config = Column(JSONB, default={}, comment="额外配置")
    extra_state = Column(JSONB, default={}, comment="额外状态")
    
    __table_args__ = (
        # 索引
        Index('ix_strategy_states_is_active', 'is_active'),
        Index('ix_strategy_states_symbol', 'symbol'),
        Index('ix_strategy_states_current_mode', 'current_mode'),
        
        {'comment': '策略状态表，存储策略运行状态'}
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """将策略状态转换为字典"""
        return {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "name": self.name,
            "symbol": self.symbol,
            "account_ids": self.account_ids,
            "is_active": self.is_active,
            "rsi_period": self.rsi_period,
            "long_levels": [self.long_level1, self.long_level2, self.long_level3],
            "short_levels": [self.short_level1, self.short_level2, self.short_level3],
            "retracement_points": self.retracement_points,
            "max_additional_positions": self.max_additional_positions,
            "fixed_stop_loss_points": self.fixed_stop_loss_points,
            "profit_taking_config": self.profit_taking_config,
            "max_holding_candles": self.max_holding_candles,
            "cooling_candles": self.cooling_candles,
            "current_mode": self.current_mode,
            "cooling_count": self.cooling_count,
            "last_signal_time": self.last_signal_time.isoformat() if self.last_signal_time else None,
            "last_trade_time": self.last_trade_time.isoformat() if self.last_trade_time else None,
            "long_monitoring": self.long_monitoring,
            "long_extreme_value": float(self.long_extreme_value) if self.long_extreme_value else None,
            "short_monitoring": self.short_monitoring,
            "short_extreme_value": float(self.short_extreme_value) if self.short_extreme_value else None,
            "update_time": self.update_time.isoformat(),
            "last_error": self.last_error
        }


class SystemConfig(Base):
    """
    系统配置表 - 存储系统运行时配置
    """
    __tablename__ = "system_configs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 配置键和值
    key = Column(String(100), nullable=False, unique=True, comment="配置键")
    value = Column(Text, nullable=True, comment="配置值")
    value_type = Column(String(20), nullable=False, default="string", comment="值类型(string, int, float, bool, json)")
    
    # 配置元数据
    description = Column(String(500), nullable=True, comment="配置描述")
    category = Column(String(50), nullable=False, default="general", comment="配置类别")
    is_sensitive = Column(Boolean, default=False, comment="是否敏感信息")
    is_editable = Column(Boolean, default=True, comment="是否可编辑")
    
    # 更新信息
    create_time = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    update_time = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    updated_by = Column(String(100), nullable=True, comment="更新人")
    
    __table_args__ = (
        # 索引
        Index('ix_system_configs_category', 'category'),
        
        {'comment': '系统配置表，存储系统运行时配置'}
    )
    
    @property
    def typed_value(self) -> Any:
        """根据类型返回正确类型的值"""
        if self.value is None:
            return None
            
        if self.value_type == "int":
            return int(self.value)
        elif self.value_type == "float":
            return float(self.value)
        elif self.value_type == "bool":
            return self.value.lower() in ("true", "1", "yes", "y", "t")
        elif self.value_type == "json":
            try:
                return json.loads(self.value)
            except:
                return {}
        else:
            return self.value


class Alert(Base):
    """
    告警记录表 - 存储系统告警信息
    """
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 告警基本信息
    alert_id = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, comment="告警UUID")
    level = Column(Enum(AlertLevel), nullable=False, default=AlertLevel.INFO, comment="告警级别")
    type = Column(Enum(AlertType), nullable=False, default=AlertType.SYSTEM, comment="告警类型")
    title = Column(String(200), nullable=False, comment="告警标题")
    message = Column(Text, nullable=False, comment="告警内容")
    
    # 关联信息
    account_id = Column(Integer, nullable=True, comment="关联账户ID")
    strategy_id = Column(String(50), nullable=True, comment="关联策略ID")
    symbol = Column(String(30), nullable=True, comment="关联交易对")
    
    # 状态信息
    is_read = Column(Boolean, default=False, comment="是否已读")
    is_handled = Column(Boolean, default=False, comment="是否已处理")
    create_time = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    read_time = Column(DateTime, nullable=True, comment="阅读时间")
    handled_time = Column(DateTime, nullable=True, comment="处理时间")
    
    # 处理信息
    handled_by = Column(String(100), nullable=True, comment="处理人")
    handling_notes = Column(String(500), nullable=True, comment="处理备注")
    
    # 额外信息
    source_ip = Column(String(50), nullable=True, comment="来源IP")
    extra_data = Column(JSONB, default={}, comment="额外数据")
    
    __table_args__ = (
        # 索引
        Index('ix_alerts_level', 'level'),
        Index('ix_alerts_type', 'type'),
        Index('ix_alerts_create_time', 'create_time'),
        Index('ix_alerts_is_read', 'is_read'),
        Index('ix_alerts_is_handled', 'is_handled'),
        Index('ix_alerts_account_id', 'account_id'),
        Index('ix_alerts_strategy_id', 'strategy_id'),
        
        {'comment': '告警记录表，存储系统告警信息'}
    )
    
    @classmethod
    def create_hypertable(cls, conn):
        """创建TimescaleDB超表"""
        # 检查是否已经是超表
        check_sql = """
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_name = 'alerts';
        """
        result = conn.execute(text(check_sql))
        if result.scalar() is None:
            # 如果不是超表，则创建
            create_sql = """
            SELECT create_hypertable('alerts', 'create_time', 
                                    chunk_time_interval => INTERVAL '1 day',
                                    if_not_exists => TRUE);
            """
            conn.execute(text(create_sql))
            
            # 创建压缩策略
            compress_sql = """
            ALTER TABLE alerts SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'level,type'
            );
            """
            conn.execute(text(compress_sql))
            
            # 设置压缩策略，7天后的数据自动压缩
            compression_policy_sql = """
            SELECT add_compression_policy('alerts', INTERVAL '7 days');
            """
            conn.execute(text(compression_policy_sql))
            
            # 设置数据保留策略，只保留30天的数据
            retention_policy_sql = """
            SELECT add_retention_policy('alerts', INTERVAL '30 days');
            """
            conn.execute(text(retention_policy_sql))
            
            print("TimescaleDB hypertable created for alerts with 30 days retention")


# 用于初始化TimescaleDB超表
def setup_timescale_hypertables(conn):
    """设置所有TimescaleDB超表"""
    Kline.create_hypertable(conn)
    Trade.create_hypertable(conn)
    Alert.create_hypertable(conn)
    print("All TimescaleDB hypertables have been set up")
