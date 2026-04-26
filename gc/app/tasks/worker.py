"""
RSI分层极值追踪自动量化交易系统 - Celery Worker任务系统

该模块实现了基于Celery的任务调度系统，包括：
- Celery应用初始化
- 定时任务配置
- K线数据收集任务
- 策略执行任务
- 账户状态同步任务
- 数据备份任务
- 系统监控任务
- 错误处理和重试机制

主要功能是自动化执行RSI分层极值追踪策略，定期收集市场数据，
并保持账户状态同步。
"""

import os
import time
import json
import logging
import asyncio
import subprocess
import shutil
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union, Tuple
import traceback
from pathlib import Path

from celery import Celery, Task
from celery.signals import task_failure, worker_ready, worker_shutdown
from celery.schedules import crontab
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_, text

from app.core.config import settings
from app.database import get_db, engine, setup_timescale_hypertables
from app.database.models import (
    Kline, TradingAccount, Position, Trade, StrategyState, 
    SystemConfig, Alert, AlertLevel, AlertType, ExchangeType,
    OrderSide, PositionSide, OrderStatus, MarginMode
)
from app.exchange import (
    ApiCredential, create_exchange, ExchangeType, Interval,
    OrderRequest, OrderSide, OrderType, MarginMode, PositionSide
)
from app.strategy import StrategyType, SignalType, StrategyMode
from app.strategy.rsi_layered import RsiLayeredStrategy
from app.utils.error_handling import (
    init_error_handling, 
    get_logger, 
    get_trace_id, 
    set_trace_id, 
    clear_trace_id,
    AppError, 
    ErrorCode,
    send_alert,
    circuit_breaker,
    retry_with_backoff
)


# 配置结构化日志
logger = get_logger("app.tasks")


# 创建Celery应用
celery_app = Celery("rsi_tracker")


# 配置Celery
def init_celery():
    """初始化Celery配置"""
    celery_app.conf.broker_url = settings.REDIS_URL
    celery_app.conf.result_backend = settings.REDIS_URL
    celery_app.conf.task_serializer = "json"
    celery_app.conf.result_serializer = "json"
    celery_app.conf.accept_content = ["json"]
    celery_app.conf.timezone = "Asia/Shanghai"
    celery_app.conf.enable_utc = True
    celery_app.conf.worker_hijack_root_logger = False
    celery_app.conf.task_track_started = True
    celery_app.conf.task_time_limit = 300  # 任务超时时间(秒)
    celery_app.conf.worker_max_tasks_per_child = 200  # 每个worker最多处理的任务数
    celery_app.conf.worker_prefetch_multiplier = 1  # 预取任务数量
    celery_app.conf.task_acks_late = True  # 任务完成后再确认
    celery_app.conf.task_reject_on_worker_lost = True  # worker丢失时拒绝任务
    celery_app.conf.task_default_queue = "default"
    celery_app.conf.task_default_exchange = "rsi_tracker"
    celery_app.conf.task_default_routing_key = "default"
    
    # 配置定时任务
    celery_app.conf.beat_schedule = {
        # K线数据收集任务 - 每分钟执行一次
        "collect_klines": {
            "task": "app.tasks.worker.collect_klines",
            "schedule": 60.0,  # 每60秒执行一次
            "options": {"queue": "data"}
        },
        
        # 策略执行任务 - 每分钟执行一次
        "execute_strategies": {
            "task": "app.tasks.worker.execute_strategies",
            "schedule": 60.0,  # 每60秒执行一次
            "options": {"queue": "strategy"}
        },
        
        # 账户状态同步任务 - 每5分钟执行一次
        "sync_account_status": {
            "task": "app.tasks.worker.sync_account_status",
            "schedule": 300.0,  # 每300秒执行一次
            "options": {"queue": "account"}
        },
        
        # 数据库清理任务 - 每天凌晨3:30执行一次
        "cleanup_database": {
            "task": "app.tasks.worker.cleanup_database",
            "schedule": crontab(hour=3, minute=30),
            "options": {"queue": "maintenance"}
        },
        
        # 数据备份任务 - 每天凌晨3:00执行一次
        "backup_data": {
            "task": "app.tasks.worker.backup_data",
            "schedule": crontab(hour=3, minute=0),
            "options": {"queue": "maintenance"}
        },
        
        # 系统监控任务 - 每10分钟执行一次
        "monitor_system": {
            "task": "app.tasks.worker.monitor_system",
            "schedule": 600.0,  # 每600秒执行一次
            "options": {"queue": "maintenance"}
        }
    }
    
    # 配置队列
    celery_app.conf.task_queues = {
        "default": {"exchange": "rsi_tracker", "routing_key": "default"},
        "data": {"exchange": "rsi_tracker", "routing_key": "data"},
        "strategy": {"exchange": "rsi_tracker", "routing_key": "strategy"},
        "account": {"exchange": "rsi_tracker", "routing_key": "account"},
        "maintenance": {"exchange": "rsi_tracker", "routing_key": "maintenance"}
    }
    
    # 配置路由
    celery_app.conf.task_routes = {
        "app.tasks.worker.collect_klines": {"queue": "data"},
        "app.tasks.worker.execute_strategies": {"queue": "strategy"},
        "app.tasks.worker.execute_strategy": {"queue": "strategy"},
        "app.tasks.worker.sync_account_status": {"queue": "account"},
        "app.tasks.worker.cleanup_database": {"queue": "maintenance"},
        "app.tasks.worker.backup_data": {"queue": "maintenance"},
        "app.tasks.worker.monitor_system": {"queue": "maintenance"}
    }
    
    logger.info("Celery配置初始化完成")


# 自定义任务基类
class BaseTask(Task):
    """自定义任务基类，提供错误处理和数据库会话管理"""
    
    _db = None
    
    @property
    def db(self) -> Session:
        """获取数据库会话"""
        if self._db is None:
            self._db = next(get_db())
        return self._db
    
    def on_success(self, retval, task_id, args, kwargs):
        """任务成功处理"""
        if self._db is not None:
            self._db.close()
            self._db = None
        # 清除跟踪ID
        clear_trace_id()
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败处理"""
        trace_id = get_trace_id()
        logger.error(
            "任务失败", 
            extra={
                "task_name": self.name,
                "task_id": task_id,
                "args": args,
                "kwargs": kwargs,
                "error": str(exc),
                "trace_id": trace_id
            },
            exc_info=True
        )
        
        # 发送告警通知
        send_alert(
            level="ERROR",
            title=f"任务失败: {self.name}",
            message=f"任务ID: {task_id}\n参数: {args}, {kwargs}\n错误: {str(exc)}",
            details={
                "task_name": self.name,
                "task_id": task_id,
                "error": str(exc),
                "trace_id": trace_id
            }
        )
        
        # 记录告警到数据库
        try:
            if self._db is not None:
                alert = Alert(
                    level=AlertLevel.ERROR,
                    type=AlertType.SYSTEM,
                    title=f"任务失败: {self.name}",
                    message=f"任务ID: {task_id}\n"
                            f"参数: args={args}, kwargs={kwargs}\n"
                            f"异常: {exc}\n"
                            f"详情: {einfo}",
                    create_time=datetime.utcnow()
                )
                self._db.add(alert)
                self._db.commit()
        except Exception as e:
            logger.error("记录任务失败告警时出错", extra={"error": str(e)}, exc_info=True)
        
        # 关闭数据库会话
        if self._db is not None:
            self._db.close()
            self._db = None
        
        # 清除跟踪ID
        clear_trace_id()


# 任务失败信号处理
@task_failure.connect
def handle_task_failure(sender=None, task_id=None, exception=None, 
                       args=None, kwargs=None, traceback=None, einfo=None, **kw):
    """处理任务失败信号"""
    trace_id = get_trace_id() or str(uuid.uuid4())
    logger.error(
        "任务失败信号", 
        extra={
            "task_name": sender.name if sender else "Unknown",
            "task_id": task_id,
            "args": args,
            "kwargs": kwargs,
            "error": str(exception),
            "trace_id": trace_id
        },
        exc_info=True
    )


# Worker就绪信号处理
@worker_ready.connect
def handle_worker_ready(sender, **kwargs):
    """处理Worker就绪信号"""
    logger.info("Worker就绪", extra={"worker": str(sender)})
    
    # 初始化错误处理系统
    try:
        init_error_handling()
        logger.info("错误处理系统初始化完成")
    except Exception as e:
        logger.error("错误处理系统初始化失败", extra={"error": str(e)}, exc_info=True)
    
    # 初始化数据库
    try:
        # 设置TimescaleDB超表
        with engine.connect() as conn:
            setup_timescale_hypertables(conn)
            logger.info("TimescaleDB超表设置完成")
    except Exception as e:
        logger.error("Worker初始化数据库失败", extra={"error": str(e)}, exc_info=True)
        # 发送告警
        send_alert(
            level="CRITICAL",
            title="Worker初始化数据库失败",
            message=f"错误: {str(e)}",
            details={"error": str(e)}
        )


# Worker关闭信号处理
@worker_shutdown.connect
def handle_worker_shutdown(sender, **kwargs):
    """处理Worker关闭信号"""
    logger.info("Worker关闭", extra={"worker": str(sender)})


# 创建交易所API客户端
@circuit_breaker("exchange_api")
async def create_exchange_client(account_id: int, db: Session) -> Any:
    """
    创建交易所API客户端
    
    Args:
        account_id: 账户ID
        db: 数据库会话
        
    Returns:
        Any: 交易所API客户端
    """
    trace_id = get_trace_id()
    try:
        # 获取账户信息
        account = db.query(TradingAccount).filter(TradingAccount.id == account_id).first()
        if not account:
            logger.error("创建交易所API客户端失败: 账户不存在", extra={
                "account_id": account_id,
                "trace_id": trace_id
            })
            return None
        
        # 创建API凭证
        credentials = ApiCredential(
            api_key=account.api_key,
            api_secret=account.api_secret,
            passphrase=account.passphrase
        )
        
        # 创建交易所客户端
        exchange_client = create_exchange(
            exchange_type=account.exchange,
            credentials=credentials,
            test_mode=settings.DEBUG_MODE
        )
        
        logger.info("创建交易所API客户端成功", extra={
            "exchange": account.exchange.value,
            "account_id": account_id,
            "trace_id": trace_id
        })
        return exchange_client
        
    except Exception as e:
        logger.error("创建交易所API客户端失败", extra={
            "account_id": account_id,
            "error": str(e),
            "trace_id": trace_id
        }, exc_info=True)
        
        # 发送告警
        send_alert(
            level="ERROR",
            title="创建交易所API客户端失败",
            message=f"账户ID: {account_id}\n错误: {str(e)}",
            details={
                "account_id": account_id,
                "error": str(e),
                "trace_id": trace_id
            }
        )
        return None


# 加载策略实例
@retry_with_backoff(max_tries=3, exceptions=(Exception,))
def load_strategy(strategy_id: str, db: Session) -> Optional[RsiLayeredStrategy]:
    """
    加载策略实例
    
    Args:
        strategy_id: 策略ID
        db: 数据库会话
        
    Returns:
        Optional[RsiLayeredStrategy]: 策略实例
    """
    trace_id = get_trace_id()
    try:
        # 获取策略状态
        strategy_state = db.query(StrategyState).filter(
            StrategyState.strategy_id == strategy_id
        ).first()
        
        if not strategy_state:
            logger.error("加载策略失败: 策略不存在", extra={
                "strategy_id": strategy_id,
                "trace_id": trace_id
            })
            return None
        
        # 创建策略实例
        strategy = RsiLayeredStrategy(
            strategy_id=strategy_state.strategy_id,
            name=strategy_state.name,
            symbol=strategy_state.symbol,
            account_ids=strategy_state.account_ids,
            rsi_period=strategy_state.rsi_period,
            long_levels=[
                strategy_state.long_level1,
                strategy_state.long_level2,
                strategy_state.long_level3
            ],
            short_levels=[
                strategy_state.short_level1,
                strategy_state.short_level2,
                strategy_state.short_level3
            ],
            retracement_points=strategy_state.retracement_points,
            max_additional_positions=strategy_state.max_additional_positions,
            fixed_stop_loss_points=strategy_state.fixed_stop_loss_points,
            profit_taking_config=strategy_state.profit_taking_config,
            max_holding_candles=strategy_state.max_holding_candles,
            cooling_candles=strategy_state.cooling_candles
        )
        
        # 从数据库状态恢复策略运行时状态
        strategy.from_dict(strategy_state.to_dict())
        
        return strategy
        
    except Exception as e:
        logger.error("加载策略失败", extra={
            "strategy_id": strategy_id,
            "error": str(e),
            "trace_id": trace_id
        }, exc_info=True)
        raise  # 重试机制会捕获异常


# 保存策略状态
@circuit_breaker("database")
def save_strategy_state(strategy: RsiLayeredStrategy, db: Session) -> bool:
    """
    保存策略状态
    
    Args:
        strategy: 策略实例
        db: 数据库会话
        
    Returns:
        bool: 是否成功
    """
    trace_id = get_trace_id()
    try:
        # 获取策略状态
        strategy_state = db.query(StrategyState).filter(
            StrategyState.strategy_id == strategy.strategy_id
        ).first()
        
        if not strategy_state:
            logger.error("保存策略状态失败: 策略不存在", extra={
                "strategy_id": strategy.strategy_id,
                "trace_id": trace_id
            })
            return False
        
        # 获取策略状态字典
        state_dict = strategy.to_dict()
        
        # 更新策略状态
        strategy_state.current_mode = state_dict["current_mode"]
        strategy_state.cooling_count = state_dict["cooling_count"]
        strategy_state.long_monitoring = state_dict["long_monitoring"]
        strategy_state.long_extreme_value = state_dict["long_extreme_value"]
        strategy_state.long_extreme_time = datetime.fromisoformat(state_dict["long_extreme_time"]) if state_dict["long_extreme_time"] else None
        strategy_state.short_monitoring = state_dict["short_monitoring"]
        strategy_state.short_extreme_value = state_dict["short_extreme_value"]
        strategy_state.short_extreme_time = datetime.fromisoformat(state_dict["short_extreme_time"]) if state_dict["short_extreme_time"] else None
        strategy_state.last_signal_time = datetime.fromisoformat(state_dict["last_signal_time"]) if state_dict["last_signal_time"] else None
        strategy_state.last_trade_time = datetime.fromisoformat(state_dict["last_trade_time"]) if state_dict["last_trade_time"] else None
        strategy_state.update_time = datetime.utcnow()
        
        # 保存到数据库
        db.commit()
        
        logger.debug("保存策略状态成功", extra={
            "strategy_id": strategy.strategy_id,
            "trace_id": trace_id
        })
        return True
        
    except Exception as e:
        logger.error("保存策略状态失败", extra={
            "strategy_id": strategy.strategy_id if strategy else "unknown",
            "error": str(e),
            "trace_id": trace_id
        }, exc_info=True)
        db.rollback()
        return False


# 处理策略信号
@circuit_breaker("exchange_trading")
async def handle_strategy_signal(
    signal: SignalType,
    strategy: RsiLayeredStrategy,
    account_id: int,
    kline: Dict[str, Any],
    db: Session
) -> bool:
    """
    处理策略信号
    
    Args:
        signal: 策略信号
        strategy: 策略实例
        account_id: 账户ID
        kline: K线数据
        db: 数据库会话
        
    Returns:
        bool: 是否成功
    """
    trace_id = get_trace_id()
    try:
        # 获取账户信息
        account = db.query(TradingAccount).filter(TradingAccount.id == account_id).first()
        if not account:
            logger.error("处理策略信号失败: 账户不存在", extra={
                "account_id": account_id,
                "strategy_id": strategy.strategy_id,
                "signal": signal.value,
                "trace_id": trace_id
            })
            return False
        
        # 创建交易所客户端
        exchange_client = await create_exchange_client(account_id, db)
        if not exchange_client:
            logger.error("处理策略信号失败: 无法创建交易所客户端", extra={
                "account_id": account_id,
                "strategy_id": strategy.strategy_id,
                "signal": signal.value,
                "trace_id": trace_id
            })
            return False
        
        # 获取当前持仓
        positions = await exchange_client.get_positions(strategy.symbol)
        current_position = None
        for pos in positions:
            if pos.symbol == strategy.symbol:
                current_position = pos
                break
        
        # 获取当前价格
        ticker = await exchange_client.get_ticker(strategy.symbol)
        current_price = ticker["last"]
        
        # 获取账户余额
        account_balance = await exchange_client.get_account_balance()
        available_balance = account_balance.available_balance
        
        # 根据信号类型处理
        if signal == SignalType.LONG_OPEN:
            # 如果有空头持仓，先平仓
            if current_position and current_position.side == PositionSide.SHORT:
                logger.info("平空头持仓", extra={
                    "symbol": strategy.symbol,
                    "account_id": account_id,
                    "trace_id": trace_id
                })
                await exchange_client.place_order(
                    OrderRequest(
                        symbol=strategy.symbol,
                        type=OrderType.MARKET,
                        side=OrderSide.BUY,  # 买入平空
                        amount=current_position.amount,
                        leverage=account.leverage,
                        margin_mode=MarginMode.CROSS,
                        position_side=PositionSide.SHORT
                    )
                )
            
            # 开多头仓位
            logger.info("开多头仓位", extra={
                "symbol": strategy.symbol,
                "account_id": account_id,
                "trace_id": trace_id
            })
            position_size = strategy.calculate_position_size(available_balance, current_price)
            
            # 设置杠杆
            await exchange_client.set_leverage(
                symbol=strategy.symbol,
                leverage=account.leverage,
                margin_mode=MarginMode.CROSS
            )
            
            # 下单
            order_response = await exchange_client.place_order(
                OrderRequest(
                    symbol=strategy.symbol,
                    type=OrderType.MARKET,
                    side=OrderSide.BUY,
                    amount=position_size,
                    leverage=account.leverage,
                    margin_mode=MarginMode.CROSS,
                    position_side=PositionSide.LONG
                )
            )
            
            # 记录交易
            trade = Trade(
                exchange_order_id=order_response.exchange_order_id,
                exchange_trade_id=order_response.exchange_order_id,
                account_id=account_id,
                symbol=strategy.symbol,
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                price=current_price,
                amount=position_size,
                value=position_size * current_price,
                strategy_id=strategy.strategy_id,
                trade_type="open",
                rsi_value=strategy.rsi_history[-1] if strategy.rsi_history else None,
                status=OrderStatus.FILLED,
                create_time=datetime.utcnow()
            )
            db.add(trade)
            
            # 更新账户余额
            account.last_update_time = datetime.utcnow()
            
            # 提交数据库事务
            db.commit()
            
            # 更新策略状态
            strategy.last_trade_time = datetime.utcnow()
            save_strategy_state(strategy, db)
            
            logger.info("多头开仓成功", extra={
                "symbol": strategy.symbol,
                "amount": position_size,
                "price": current_price,
                "account_id": account_id,
                "trace_id": trace_id
            })
            return True
            
        elif signal == SignalType.SHORT_OPEN:
            # 如果有多头持仓，先平仓
            if current_position and current_position.side == PositionSide.LONG:
                logger.info("平多头持仓", extra={
                    "symbol": strategy.symbol,
                    "account_id": account_id,
                    "trace_id": trace_id
                })
                await exchange_client.place_order(
                    OrderRequest(
                        symbol=strategy.symbol,
                        type=OrderType.MARKET,
                        side=OrderSide.SELL,  # 卖出平多
                        amount=current_position.amount,
                        leverage=account.leverage,
                        margin_mode=MarginMode.CROSS,
                        position_side=PositionSide.LONG
                    )
                )
            
            # 开空头仓位
            logger.info("开空头仓位", extra={
                "symbol": strategy.symbol,
                "account_id": account_id,
                "trace_id": trace_id
            })
            position_size = strategy.calculate_position_size(available_balance, current_price)
            
            # 设置杠杆
            await exchange_client.set_leverage(
                symbol=strategy.symbol,
                leverage=account.leverage,
                margin_mode=MarginMode.CROSS
            )
            
            # 下单
            order_response = await exchange_client.place_order(
                OrderRequest(
                    symbol=strategy.symbol,
                    type=OrderType.MARKET,
                    side=OrderSide.SELL,
                    amount=position_size,
                    leverage=account.leverage,
                    margin_mode=MarginMode.CROSS,
                    position_side=PositionSide.SHORT
                )
            )
            
            # 记录交易
            trade = Trade(
                exchange_order_id=order_response.exchange_order_id,
                exchange_trade_id=order_response.exchange_order_id,
                account_id=account_id,
                symbol=strategy.symbol,
                side=OrderSide.SELL,
                type=OrderType.MARKET,
                price=current_price,
                amount=position_size,
                value=position_size * current_price,
                strategy_id=strategy.strategy_id,
                trade_type="open",
                rsi_value=strategy.rsi_history[-1] if strategy.rsi_history else None,
                status=OrderStatus.FILLED,
                create_time=datetime.utcnow()
            )
            db.add(trade)
            
            # 更新账户余额
            account.last_update_time = datetime.utcnow()
            
            # 提交数据库事务
            db.commit()
            
            # 更新策略状态
            strategy.last_trade_time = datetime.utcnow()
            save_strategy_state(strategy, db)
            
            logger.info("空头开仓成功", extra={
                "symbol": strategy.symbol,
                "amount": position_size,
                "price": current_price,
                "account_id": account_id,
                "trace_id": trace_id
            })
            return True
            
        elif signal == SignalType.LONG_ADD:
            # 确保有多头持仓
            if not current_position or current_position.side != PositionSide.LONG:
                logger.warning("多头加仓失败: 没有多头持仓", extra={
                    "account_id": account_id,
                    "trace_id": trace_id
                })
                return False
            
            # 获取当前持仓信息
            position_info = db.query(Position).filter(
                Position.account_id == account_id,
                Position.symbol == strategy.symbol,
                Position.side == PositionSide.LONG
            ).first()
            
            if not position_info:
                logger.warning("多头加仓失败: 数据库中没有持仓记录", extra={
                    "account_id": account_id,
                    "trace_id": trace_id
                })
                return False
            
            # 检查是否已达到最大加仓次数
            if position_info.additional_positions_count >= strategy.max_additional_positions:
                logger.warning("多头加仓失败: 已达到最大加仓次数", extra={
                    "account_id": account_id,
                    "current_count": position_info.additional_positions_count,
                    "max_count": strategy.max_additional_positions,
                    "trace_id": trace_id
                })
                return False
            
            # 计算加仓数量
            add_size = strategy.calculate_position_size(available_balance, current_price) * 0.5  # 加仓数量为标准开仓的一半
            
            # 下单
            order_response = await exchange_client.place_order(
                OrderRequest(
                    symbol=strategy.symbol,
                    type=OrderType.MARKET,
                    side=OrderSide.BUY,
                    amount=add_size,
                    leverage=account.leverage,
                    margin_mode=MarginMode.CROSS,
                    position_side=PositionSide.LONG
                )
            )
            
            # 记录交易
            trade = Trade(
                exchange_order_id=order_response.exchange_order_id,
                exchange_trade_id=order_response.exchange_order_id,
                account_id=account_id,
                symbol=strategy.symbol,
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                price=current_price,
                amount=add_size,
                value=add_size * current_price,
                strategy_id=strategy.strategy_id,
                position_id=position_info.id,
                trade_type="add",
                rsi_value=strategy.rsi_history[-1] if strategy.rsi_history else None,
                rsi_extreme=strategy.long_extreme_value,
                rsi_retracement=strategy.rsi_history[-1] - strategy.long_extreme_value if strategy.rsi_history and strategy.long_extreme_value else None,
                status=OrderStatus.FILLED,
                create_time=datetime.utcnow()
            )
            db.add(trade)
            
            # 更新持仓信息
            position_info.additional_positions_count += 1
            position_info.size += add_size
            position_info.last_update_time = datetime.utcnow()
            
            # 更新账户余额
            account.last_update_time = datetime.utcnow()
            
            # 提交数据库事务
            db.commit()
            
            # 更新策略状态
            strategy.last_trade_time = datetime.utcnow()
            save_strategy_state(strategy, db)
            
            logger.info("多头加仓成功", extra={
                "symbol": strategy.symbol,
                "amount": add_size,
                "price": current_price,
                "add_count": position_info.additional_positions_count,
                "max_count": strategy.max_additional_positions,
                "account_id": account_id,
                "trace_id": trace_id
            })
            return True
            
        elif signal == SignalType.SHORT_ADD:
            # 确保有空头持仓
            if not current_position or current_position.side != PositionSide.SHORT:
                logger.warning("空头加仓失败: 没有空头持仓", extra={
                    "account_id": account_id,
                    "trace_id": trace_id
                })
                return False
            
            # 获取当前持仓信息
            position_info = db.query(Position).filter(
                Position.account_id == account_id,
                Position.symbol == strategy.symbol,
                Position.side == PositionSide.SHORT
            ).first()
            
            if not position_info:
                logger.warning("空头加仓失败: 数据库中没有持仓记录", extra={
                    "account_id": account_id,
                    "trace_id": trace_id
                })
                return False
            
            # 检查是否已达到最大加仓次数
            if position_info.additional_positions_count >= strategy.max_additional_positions:
                logger.warning("空头加仓失败: 已达到最大加仓次数", extra={
                    "account_id": account_id,
                    "current_count": position_info.additional_positions_count,
                    "max_count": strategy.max_additional_positions,
                    "trace_id": trace_id
                })
                return False
            
            # 计算加仓数量
            add_size = strategy.calculate_position_size(available_balance, current_price) * 0.5  # 加仓数量为标准开仓的一半
            
            # 下单
            order_response = await exchange_client.place_order(
                OrderRequest(
                    symbol=strategy.symbol,
                    type=OrderType.MARKET,
                    side=OrderSide.SELL,
                    amount=add_size,
                    leverage=account.leverage,
                    margin_mode=MarginMode.CROSS,
                    position_side=PositionSide.SHORT
                )
            )
            
            # 记录交易
            trade = Trade(
                exchange_order_id=order_response.exchange_order_id,
                exchange_trade_id=order_response.exchange_order_id,
                account_id=account_id,
                symbol=strategy.symbol,
                side=OrderSide.SELL,
                type=OrderType.MARKET,
                price=current_price,
                amount=add_size,
                value=add_size * current_price,
                strategy_id=strategy.strategy_id,
                position_id=position_info.id,
                trade_type="add",
                rsi_value=strategy.rsi_history[-1] if strategy.rsi_history else None,
                rsi_extreme=strategy.short_extreme_value,
                rsi_retracement=strategy.short_extreme_value - strategy.rsi_history[-1] if strategy.rsi_history and strategy.short_extreme_value else None,
                status=OrderStatus.FILLED,
                create_time=datetime.utcnow()
            )
            db.add(trade)
            
            # 更新持仓信息
            position_info.additional_positions_count += 1
            position_info.size += add_size
            position_info.last_update_time = datetime.utcnow()
            
            # 更新账户余额
            account.last_update_time = datetime.utcnow()
            
            # 提交数据库事务
            db.commit()
            
            # 更新策略状态
            strategy.last_trade_time = datetime.utcnow()
            save_strategy_state(strategy, db)
            
            logger.info("空头加仓成功", extra={
                "symbol": strategy.symbol,
                "amount": add_size,
                "price": current_price,
                "add_count": position_info.additional_positions_count,
                "max_count": strategy.max_additional_positions,
                "account_id": account_id,
                "trace_id": trace_id
            })
            return True
            
        elif signal in [SignalType.TAKE_PROFIT, SignalType.STOP_LOSS, SignalType.TIMEOUT_CLOSE]:
            # 确保有持仓
            if not current_position:
                logger.warning("平仓失败: 没有持仓", extra={
                    "account_id": account_id,
                    "trace_id": trace_id
                })
                return False
            
            # 获取当前持仓信息
            position_info = db.query(Position).filter(
                Position.account_id == account_id,
                Position.symbol == strategy.symbol,
                Position.side == (PositionSide.LONG if current_position.side == PositionSide.LONG else PositionSide.SHORT)
            ).first()
            
            # 平仓
            logger.info("平仓", extra={
                "symbol": strategy.symbol,
                "direction": "多" if current_position.side == PositionSide.LONG else "空",
                "reason": signal.value,
                "account_id": account_id,
                "trace_id": trace_id
            })
            
            # 下单
            order_response = await exchange_client.place_order(
                OrderRequest(
                    symbol=strategy.symbol,
                    type=OrderType.MARKET,
                    side=OrderSide.SELL if current_position.side == PositionSide.LONG else OrderSide.BUY,
                    amount=current_position.amount,
                    leverage=account.leverage,
                    margin_mode=MarginMode.CROSS,
                    position_side=current_position.side
                )
            )
            
            # 记录交易
            trade = Trade(
                exchange_order_id=order_response.exchange_order_id,
                exchange_trade_id=order_response.exchange_order_id,
                account_id=account_id,
                symbol=strategy.symbol,
                side=OrderSide.SELL if current_position.side == PositionSide.LONG else OrderSide.BUY,
                type=OrderType.MARKET,
                price=current_price,
                amount=current_position.amount,
                value=current_position.amount * current_price,
                strategy_id=strategy.strategy_id,
                position_id=position_info.id if position_info else None,
                trade_type=signal.value.split('_')[0],  # take/stop/timeout
                rsi_value=strategy.rsi_history[-1] if strategy.rsi_history else None,
                holding_periods=position_info.holding_periods if position_info else None,
                pnl=current_position.unrealized_pnl,
                status=OrderStatus.FILLED,
                create_time=datetime.utcnow()
            )
            db.add(trade)
            
            # 更新账户余额
            account.last_update_time = datetime.utcnow()
            
            # 如果有持仓记录，标记为已关闭
            if position_info:
                # 保存持仓记录到历史表或做其他处理
                position_info.last_update_time = datetime.utcnow()
            
            # 提交数据库事务
            db.commit()
            
            # 更新策略状态
            strategy.last_trade_time = datetime.utcnow()
            save_strategy_state(strategy, db)
            
            logger.info("平仓成功", extra={
                "symbol": strategy.symbol,
                "amount": current_position.amount,
                "price": current_price,
                "pnl": current_position.unrealized_pnl,
                "account_id": account_id,
                "trace_id": trace_id
            })
            return True
            
        elif signal == SignalType.REVERSE_TRADE:
            # 确保有持仓
            if not current_position:
                logger.warning("反手交易失败: 没有持仓", extra={
                    "account_id": account_id,
                    "trace_id": trace_id
                })
                return False
            
            # 获取当前持仓信息
            position_info = db.query(Position).filter(
                Position.account_id == account_id,
                Position.symbol == strategy.symbol,
                Position.side == (PositionSide.LONG if current_position.side == PositionSide.LONG else PositionSide.SHORT)
            ).first()
            
            # 先平仓
            logger.info("反手交易-平仓", extra={
                "symbol": strategy.symbol,
                "direction": "多" if current_position.side == PositionSide.LONG else "空",
                "account_id": account_id,
                "trace_id": trace_id
            })
            
            # 下单平仓
            await exchange_client.place_order(
                OrderRequest(
                    symbol=strategy.symbol,
                    type=OrderType.MARKET,
                    side=OrderSide.SELL if current_position.side == PositionSide.LONG else OrderSide.BUY,
                    amount=current_position.amount,
                    leverage=account.leverage,
                    margin_mode=MarginMode.CROSS,
                    position_side=current_position.side
                )
            )
            
            # 记录平仓交易
            close_trade = Trade(
                exchange_order_id=f"close_{int(time.time()*1000)}",
                exchange_trade_id=f"close_{int(time.time()*1000)}",
                account_id=account_id,
                symbol=strategy.symbol,
                side=OrderSide.SELL if current_position.side == PositionSide.LONG else OrderSide.BUY,
                type=OrderType.MARKET,
                price=current_price,
                amount=current_position.amount,
                value=current_position.amount * current_price,
                strategy_id=strategy.strategy_id,
                position_id=position_info.id if position_info else None,
                trade_type="reverse_close",
                rsi_value=strategy.rsi_history[-1] if strategy.rsi_history else None,
                holding_periods=position_info.holding_periods if position_info else None,
                pnl=current_position.unrealized_pnl,
                status=OrderStatus.FILLED,
                create_time=datetime.utcnow()
            )
            db.add(close_trade)
            
            # 然后开反向仓位
            logger.info("反手交易-开仓", extra={
                "symbol": strategy.symbol,
                "direction": "空" if current_position.side == PositionSide.LONG else "多",
                "account_id": account_id,
                "trace_id": trace_id
            })
            
            # 计算开仓数量
            position_size = strategy.calculate_position_size(available_balance, current_price)
            
            # 设置杠杆
            await exchange_client.set_leverage(
                symbol=strategy.symbol,
                leverage=account.leverage,
                margin_mode=MarginMode.CROSS
            )
            
            # 下单开仓
            new_side = OrderSide.SELL if current_position.side == PositionSide.LONG else OrderSide.BUY
            new_position_side = PositionSide.SHORT if current_position.side == PositionSide.LONG else PositionSide.LONG
            
            order_response = await exchange_client.place_order(
                OrderRequest(
                    symbol=strategy.symbol,
                    type=OrderType.MARKET,
                    side=new_side,
                    amount=position_size,
                    leverage=account.leverage,
                    margin_mode=MarginMode.CROSS,
                    position_side=new_position_side
                )
            )
            
            # 记录开仓交易
            open_trade = Trade(
                exchange_order_id=order_response.exchange_order_id,
                exchange_trade_id=order_response.exchange_order_id,
                account_id=account_id,
                symbol=strategy.symbol,
                side=new_side,
                type=OrderType.MARKET,
                price=current_price,
                amount=position_size,
                value=position_size * current_price,
                strategy_id=strategy.strategy_id,
                trade_type="reverse_open",
                rsi_value=strategy.rsi_history[-1] if strategy.rsi_history else None,
                status=OrderStatus.FILLED,
                create_time=datetime.utcnow()
            )
            db.add(open_trade)
            
            # 更新账户余额
            account.last_update_time = datetime.utcnow()
            
            # 如果有持仓记录，标记为已关闭
            if position_info:
                # 保存持仓记录到历史表或做其他处理
                position_info.last_update_time = datetime.utcnow()
            
            # 提交数据库事务
            db.commit()
            
            # 更新策略状态
            strategy.last_trade_time = datetime.utcnow()
            save_strategy_state(strategy, db)
            
            logger.info("反手交易成功", extra={
                "symbol": strategy.symbol,
                "close_amount": current_position.amount,
                "open_amount": position_size,
                "price": current_price,
                "account_id": account_id,
                "trace_id": trace_id
            })
            return True
        
        else:
            logger.warning("未处理的信号类型", extra={
                "signal": signal.value,
                "trace_id": trace_id
            })
            return False
        
    except Exception as e:
        logger.error("处理策略信号失败", extra={
            "signal": signal.value if signal else "unknown",
            "strategy_id": strategy.strategy_id if strategy else "unknown",
            "account_id": account_id,
            "error": str(e),
            "trace_id": trace_id
        }, exc_info=True)
        
        # 发送告警
        send_alert(
            level="ERROR",
            title="处理策略信号失败",
            message=f"策略ID: {strategy.strategy_id if strategy else 'unknown'}\n"
                    f"账户ID: {account_id}\n"
                    f"信号: {signal.value if signal else 'unknown'}\n"
                    f"错误: {str(e)}",
            details={
                "strategy_id": strategy.strategy_id if strategy else "unknown",
                "account_id": account_id,
                "signal": signal.value if signal else "unknown",
                "error": str(e),
                "trace_id": trace_id
            }
        )
        
        db.rollback()
        return False
    finally:
        # 关闭交易所客户端
        if exchange_client:
            await exchange_client.close()


# K线数据收集任务
@celery_app.task(bind=True, base=BaseTask)
def collect_klines(self):
    """收集K线数据任务"""
    # 生成任务跟踪ID
    trace_id = str(uuid.uuid4())
    set_trace_id(trace_id)
    
    logger.info("开始收集K线数据", extra={"trace_id": trace_id})
    
    try:
        # 获取活跃账户
        accounts = self.db.query(TradingAccount).filter(TradingAccount.is_active == True).all()
        if not accounts:
            logger.warning("没有活跃账户，跳过K线数据收集", extra={"trace_id": trace_id})
            return {"status": "skipped", "reason": "no_active_accounts", "trace_id": trace_id}
        
        # 获取活跃策略
        strategies = self.db.query(StrategyState).filter(StrategyState.is_active == True).all()
        if not strategies:
            logger.warning("没有活跃策略，跳过K线数据收集", extra={"trace_id": trace_id})
            return {"status": "skipped", "reason": "no_active_strategies", "trace_id": trace_id}
        
        # 收集每个策略的K线数据
        for strategy in strategies:
            # 选择一个账户来获取数据
            account = accounts[0]  # 简单起见，使用第一个账户
            
            # 创建异步事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # 创建交易所客户端
                exchange_client = loop.run_until_complete(create_exchange_client(account.id, self.db))
                if not exchange_client:
                    logger.error("创建交易所客户端失败，跳过K线数据收集", extra={
                        "symbol": strategy.symbol,
                        "trace_id": trace_id
                    })
                    continue
                
                # 获取K线数据
                klines = loop.run_until_complete(
                    exchange_client.get_klines(
                        symbol=strategy.symbol,
                        interval=Interval.MIN1,
                        limit=2  # 只获取最新的2根K线
                    )
                )
                
                # 关闭交易所客户端
                loop.run_until_complete(exchange_client.close())
                
                # 处理K线数据
                if klines:
                    # 只保存最新的一根K线
                    latest_kline = klines[-1]
                    
                    # 检查是否已存在
                    existing_kline = self.db.query(Kline).filter(
                        Kline.exchange == account.exchange,
                        Kline.symbol == strategy.symbol,
                        Kline.timestamp == latest_kline.open_time,
                        Kline.interval == latest_kline.interval
                    ).first()
                    
                    if not existing_kline:
                        # 创建新的K线记录
                        kline_record = Kline(
                            exchange=account.exchange,
                            symbol=strategy.symbol,
                            interval=latest_kline.interval,
                            timestamp=latest_kline.open_time,
                            open=latest_kline.open,
                            high=latest_kline.high,
                            low=latest_kline.low,
                            close=latest_kline.close,
                            volume=latest_kline.volume,
                            quote_volume=latest_kline.quote_volume,
                            trades_count=latest_kline.trades_count
                        )
                        self.db.add(kline_record)
                        self.db.commit()
                        
                        logger.debug("保存K线数据", extra={
                            "symbol": strategy.symbol,
                            "timestamp": latest_kline.open_time.isoformat(),
                            "trace_id": trace_id
                        })
                    else:
                        # 更新现有K线记录
                        existing_kline.open = latest_kline.open
                        existing_kline.high = latest_kline.high
                        existing_kline.low = latest_kline.low
                        existing_kline.close = latest_kline.close
                        existing_kline.volume = latest_kline.volume
                        existing_kline.quote_volume = latest_kline.quote_volume
                        existing_kline.trades_count = latest_kline.trades_count
                        self.db.commit()
                        
                        logger.debug("更新K线数据", extra={
                            "symbol": strategy.symbol,
                            "timestamp": latest_kline.open_time.isoformat(),
                            "trace_id": trace_id
                        })
                    
                    # 计算RSI
                    # 获取历史K线数据
                    history_klines = self.db.query(Kline).filter(
                        Kline.exchange == account.exchange,
                        Kline.symbol == strategy.symbol,
                        Kline.interval == latest_kline.interval
                    ).order_by(Kline.timestamp.desc()).limit(50).all()  # 获取最近50根K线
                    
                    if len(history_klines) >= 14:  # 至少需要14根K线才能计算RSI
                        # 准备计算RSI的收盘价列表
                        close_prices = [float(k.close) for k in reversed(history_klines)]
                        
                        # 创建策略实例来计算RSI
                        temp_strategy = RsiLayeredStrategy(
                            strategy_id=strategy.strategy_id,
                            name=strategy.name,
                            symbol=strategy.symbol,
                            account_ids=strategy.account_ids,
                            rsi_period=strategy.rsi_period
                        )
                        
                        # 计算RSI
                        rsi_value = temp_strategy.calculate_rsi(close_prices)
                        
                        # 更新K线记录的RSI值
                        existing_kline = self.db.query(Kline).filter(
                            Kline.exchange == account.exchange,
                            Kline.symbol == strategy.symbol,
                            Kline.timestamp == latest_kline.open_time,
                            Kline.interval == latest_kline.interval
                        ).first()
                        
                        if existing_kline:
                            existing_kline.rsi_14 = rsi_value
                            self.db.commit()
                            
                            logger.debug("更新RSI值", extra={
                                "symbol": strategy.symbol,
                                "timestamp": latest_kline.open_time.isoformat(),
                                "rsi": round(rsi_value, 2),
                                "trace_id": trace_id
                            })
                
            except Exception as e:
                logger.error("收集K线数据失败", extra={
                    "symbol": strategy.symbol,
                    "error": str(e),
                    "trace_id": trace_id
                }, exc_info=True)
                self.db.rollback()
            finally:
                # 关闭事件循环
                loop.close()
        
        logger.info("K线数据收集完成", extra={"trace_id": trace_id})
        return {"status": "success", "trace_id": trace_id}
        
    except Exception as e:
        logger.error("K线数据收集任务失败", extra={
            "error": str(e),
            "trace_id": trace_id
        }, exc_info=True)
        
        # 发送告警
        send_alert(
            level="ERROR",
            title="K线数据收集任务失败",
            message=f"错误: {str(e)}",
            details={
                "error": str(e),
                "trace_id": trace_id
            }
        )
        
        return {"status": "error", "error": str(e), "trace_id": trace_id}


# 策略执行任务
@celery_app.task(bind=True, base=BaseTask)
def execute_strategies(self):
    """执行所有活跃策略"""
    # 生成任务跟踪ID
    trace_id = str(uuid.uuid4())
    set_trace_id(trace_id)
    
    logger.info("开始执行策略", extra={"trace_id": trace_id})
    
    try:
        # 获取活跃策略
        strategies = self.db.query(StrategyState).filter(StrategyState.is_active == True).all()
        if not strategies:
            logger.warning("没有活跃策略，跳过策略执行", extra={"trace_id": trace_id})
            return {"status": "skipped", "reason": "no_active_strategies", "trace_id": trace_id}
        
        # 执行每个策略
        for strategy_state in strategies:
            # 启动异步任务执行策略
            execute_strategy.delay(strategy_state.strategy_id)
        
        logger.info("已启动策略执行任务", extra={
            "count": len(strategies),
            "trace_id": trace_id
        })
        return {"status": "success", "count": len(strategies), "trace_id": trace_id}
        
    except Exception as e:
        logger.error("策略执行任务失败", extra={
            "error": str(e),
            "trace_id": trace_id
        }, exc_info=True)
        
        # 发送告警
        send_alert(
            level="ERROR",
            title="策略执行任务失败",
            message=f"错误: {str(e)}",
            details={
                "error": str(e),
                "trace_id": trace_id
            }
        )
        
        return {"status": "error", "error": str(e), "trace_id": trace_id}


# 单个策略执行任务
@celery_app.task(bind=True, base=BaseTask)
def execute_strategy(self, strategy_id: str):
    """
    执行单个策略
    
    Args:
        strategy_id: 策略ID
    """
    # 生成任务跟踪ID
    trace_id = str(uuid.uuid4())
    set_trace_id(trace_id)
    
    logger.info("开始执行策略", extra={
        "strategy_id": strategy_id,
        "trace_id": trace_id
    })
    
    try:
        # 加载策略实例
        strategy = load_strategy(strategy_id, self.db)
        if not strategy:
            logger.error("加载策略失败", extra={
                "strategy_id": strategy_id,
                "trace_id": trace_id
            })
            return {"status": "error", "reason": "strategy_not_found", "trace_id": trace_id}
        
        # 获取策略状态
        strategy_state = self.db.query(StrategyState).filter(
            StrategyState.strategy_id == strategy_id
        ).first()
        
        if not strategy_state:
            logger.error("获取策略状态失败", extra={
                "strategy_id": strategy_id,
                "trace_id": trace_id
            })
            return {"status": "error", "reason": "strategy_state_not_found", "trace_id": trace_id}
        
        # 检查策略是否活跃
        if not strategy_state.is_active:
            logger.warning("策略未激活，跳过执行", extra={
                "strategy_id": strategy_id,
                "trace_id": trace_id
            })
            return {"status": "skipped", "reason": "strategy_not_active", "trace_id": trace_id}
        
        # 获取最新K线数据
        latest_kline = self.db.query(Kline).filter(
            Kline.symbol == strategy.symbol,
            Kline.interval == "1m"
        ).order_by(Kline.timestamp.desc()).first()
        
        if not latest_kline:
            logger.warning("没有K线数据，跳过策略执行", extra={
                "strategy_id": strategy_id,
                "trace_id": trace_id
            })
            return {"status": "skipped", "reason": "no_kline_data", "trace_id": trace_id}
        
        # 获取历史K线数据
        history_klines = self.db.query(Kline).filter(
            Kline.symbol == strategy.symbol,
            Kline.interval == "1m"
        ).order_by(Kline.timestamp.desc()).limit(50).all()  # 获取最近50根K线
        
        # 准备K线数据
        kline_data = {
            "open": float(latest_kline.open),
            "high": float(latest_kline.high),
            "low": float(latest_kline.low),
            "close": float(latest_kline.close),
            "volume": float(latest_kline.volume),
            "timestamp": int(latest_kline.timestamp.timestamp() * 1000)  # 转换为毫秒时间戳
        }
        
        # 更新策略的K线历史
        strategy.kline_history = []  # 清空历史
        for kline in reversed(history_klines):
            strategy.kline_history.append(float(kline.close))
        
        # 如果有RSI值，直接使用
        if latest_kline.rsi_14 is not None:
            strategy.rsi_history.append(float(latest_kline.rsi_14))
        
        # 处理K线数据
        signal = strategy.process_kline(kline_data)
        
        # 更新策略状态
        strategy_state.update_time = datetime.utcnow()
        save_strategy_state(strategy, self.db)
        
        # 如果没有信号，直接返回
        if not signal:
            logger.debug("策略没有产生信号", extra={
                "strategy_id": strategy_id,
                "trace_id": trace_id
            })
            return {"status": "success", "signal": None, "trace_id": trace_id}
        
        logger.info("策略产生信号", extra={
            "strategy_id": strategy_id,
            "signal": signal.value,
            "trace_id": trace_id
        })
        
        # 获取关联账户
        for account_id in strategy.account_ids:
            # 检查账户是否活跃
            account = self.db.query(TradingAccount).filter(
                TradingAccount.id == account_id,
                TradingAccount.is_active == True
            ).first()
            
            if not account:
                logger.warning("账户未激活或不存在，跳过信号处理", extra={
                    "account_id": account_id,
                    "trace_id": trace_id
                })
                continue
            
            # 创建异步事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # 处理策略信号
                result = loop.run_until_complete(
                    handle_strategy_signal(
                        signal=signal,
                        strategy=strategy,
                        account_id=account_id,
                        kline=kline_data,
                        db=self.db
                    )
                )
                
                if result:
                    logger.info("信号处理成功", extra={
                        "strategy_id": strategy_id,
                        "signal": signal.value,
                        "account_id": account_id,
                        "trace_id": trace_id
                    })
                else:
                    logger.warning("信号处理失败", extra={
                        "strategy_id": strategy_id,
                        "signal": signal.value,
                        "account_id": account_id,
                        "trace_id": trace_id
                    })
                
            except Exception as e:
                logger.error("处理策略信号时发生错误", extra={
                    "strategy_id": strategy_id,
                    "signal": signal.value,
                    "account_id": account_id,
                    "error": str(e),
                    "trace_id": trace_id
                }, exc_info=True)
            finally:
                # 关闭事件循环
                loop.close()
        
        # 更新持仓K线数
        positions = self.db.query(Position).filter(
            Position.symbol == strategy.symbol,
            Position.strategy_id == strategy_id
        ).all()
        
        for position in positions:
            position.holding_periods += 1
            self.db.commit()
        
        logger.info("策略执行完成", extra={
            "strategy_id": strategy_id,
            "trace_id": trace_id
        })
        return {"status": "success", "signal": signal.value if signal else None, "trace_id": trace_id}
        
    except Exception as e:
        logger.error("策略执行失败", extra={
            "strategy_id": strategy_id,
            "error": str(e),
            "trace_id": trace_id
        }, exc_info=True)
        
        # 发送告警
        send_alert(
            level="ERROR",
            title="策略执行失败",
            message=f"策略ID: {strategy_id}\n错误: {str(e)}",
            details={
                "strategy_id": strategy_id,
                "error": str(e),
                "trace_id": trace_id
            }
        )
        
        return {"status": "error", "error": str(e), "trace_id": trace_id}


# 账户状态同步任务
@celery_app.task(bind=True, base=BaseTask)
def sync_account_status(self):
    """同步账户状态"""
    # 生成任务跟踪ID
    trace_id = str(uuid.uuid4())
    set_trace_id(trace_id)
    
    logger.info("开始同步账户状态", extra={"trace_id": trace_id})
    
    try:
        # 获取活跃账户
        accounts = self.db.query(TradingAccount).filter(TradingAccount.is_active == True).all()
        if not accounts:
            logger.warning("没有活跃账户，跳过账户状态同步", extra={"trace_id": trace_id})
            return {"status": "skipped", "reason": "no_active_accounts", "trace_id": trace_id}
        
        # 同步每个账户的状态
        for account in accounts:
            # 创建异步事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # 创建交易所客户端
                exchange_client = loop.run_until_complete(create_exchange_client(account.id, self.db))
                if not exchange_client:
                    logger.error("创建交易所客户端失败，跳过账户状态同步", extra={
                        "account_id": account.id,
                        "trace_id": trace_id
                    })
                    continue
                
                # 获取账户余额
                balance = loop.run_until_complete(exchange_client.get_account_balance())
                
                # 获取持仓信息
                positions = loop.run_until_complete(exchange_client.get_positions())
                
                # 关闭交易所客户端
                loop.run_until_complete(exchange_client.close())
                
                # 更新账户余额
                account.total_equity_usdt = balance.total_equity
                account.available_balance_usdt = balance.available_balance
                account.margin_balance_usdt = balance.margin_balance
                account.unrealized_pnl_usdt = balance.unrealized_pnl
                account.last_sync_time = datetime.utcnow()
                account.last_update_time = datetime.utcnow()
                account.error_message = None
                
                # 更新持仓信息
                for pos in positions:
                    # 检查是否已存在持仓记录
                    position = self.db.query(Position).filter(
                        Position.account_id == account.id,
                        Position.symbol == pos.symbol,
                        Position.side == pos.side
                    ).first()
                    
                    if position:
                        # 更新现有持仓
                        position.size = pos.amount
                        position.entry_price = pos.entry_price
                        position.mark_price = pos.mark_price
                        position.liquidation_price = pos.liquidation_price
                        position.leverage = pos.leverage
                        position.margin_mode = pos.margin_mode.value
                        position.unrealized_pnl = pos.unrealized_pnl
                        position.realized_pnl = pos.realized_pnl
                        position.initial_margin = pos.initial_margin
                        position.position_margin = pos.position_margin
                        position.last_update_time = datetime.utcnow()
                    else:
                        # 创建新持仓记录
                        new_position = Position(
                            account_id=account.id,
                            symbol=pos.symbol,
                            side=pos.side,
                            size=pos.amount,
                            leverage=pos.leverage,
                            entry_price=pos.entry_price,
                            mark_price=pos.mark_price,
                            liquidation_price=pos.liquidation_price,
                            unrealized_pnl=pos.unrealized_pnl,
                            realized_pnl=pos.realized_pnl,
                            margin_mode=pos.margin_mode.value,
                            initial_margin=pos.initial_margin,
                            position_margin=pos.position_margin,
                            open_time=datetime.utcnow(),
                            holding_periods=0,
                            additional_positions_count=0,
                            max_profit=0,
                            last_update_time=datetime.utcnow()
                        )
                        self.db.add(new_position)
                
                # 删除已平仓的持仓记录
                existing_positions = self.db.query(Position).filter(
                    Position.account_id == account.id
                ).all()
                
                for existing_pos in existing_positions:
                    found = False
                    for pos in positions:
                        if existing_pos.symbol == pos.symbol and existing_pos.side == pos.side:
                            found = True
                            break
                    
                    if not found:
                        # 持仓已平仓，删除记录
                        self.db.delete(existing_pos)
                
                # 提交数据库事务
                self.db.commit()
                
                logger.info("账户状态同步成功", extra={
                    "account_id": account.id,
                    "account_name": account.name,
                    "trace_id": trace_id
                })
                
            except Exception as e:
                logger.error("同步账户状态失败", extra={
                    "account_id": account.id,
                    "error": str(e),
                    "trace_id": trace_id
                }, exc_info=True)
                
                # 更新错误信息
                account.error_message = str(e)
                account.last_update_time = datetime.utcnow()
                self.db.commit()
                
                # 记录告警
                alert = Alert(
                    level=AlertLevel.ERROR,
                    type=AlertType.ACCOUNT,
                    title=f"账户状态同步失败: {account.name}",
                    message=f"账户ID: {account.id}\n"
                            f"交易所: {account.exchange.value}\n"
                            f"错误: {str(e)}",
                    account_id=account.id,
                    create_time=datetime.utcnow()
                )
                self.db.add(alert)
                self.db.commit()
                
                # 发送告警
                send_alert(
                    level="ERROR",
                    title=f"账户状态同步失败: {account.name}",
                    message=f"账户ID: {account.id}\n"
                            f"交易所: {account.exchange.value}\n"
                            f"错误: {str(e)}",
                    details={
                        "account_id": account.id,
                        "account_name": account.name,
                        "exchange": account.exchange.value,
                        "error": str(e),
                        "trace_id": trace_id
                    }
                )
                
            finally:
                # 关闭事件循环
                loop.close()
        
        logger.info("账户状态同步完成", extra={"trace_id": trace_id})
        return {"status": "success", "trace_id": trace_id}
        
    except Exception as e:
        logger.error("账户状态同步任务失败", extra={
            "error": str(e),
            "trace_id": trace_id
        }, exc_info=True)
        
        # 发送告警
        send_alert(
            level="ERROR",
            title="账户状态同步任务失败",
            message=f"错误: {str(e)}",
            details={
                "error": str(e),
                "trace_id": trace_id
            }
        )
        
        return {"status": "error", "error": str(e), "trace_id": trace_id}


# 数据库清理任务
@celery_app.task(bind=True, base=BaseTask)
def cleanup_database(self):
    """清理数据库过期数据"""
    # 生成任务跟踪ID
    trace_id = str(uuid.uuid4())
    set_trace_id(trace_id)
    
    logger.info("开始清理数据库", extra={"trace_id": trace_id})
    
    try:
        # 清理K线数据
        retention_days = settings.DATA_RETENTION_DAYS
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        # 使用TimescaleDB的保留策略，不需要手动删除
        # 这里只记录日志
        logger.info("K线数据保留策略", extra={
            "retention_days": retention_days,
            "trace_id": trace_id
        })
        
        # 清理交易记录
        trade_retention_days = settings.TRADE_LOG_RETENTION_DAYS
        trade_cutoff_date = datetime.utcnow() - timedelta(days=trade_retention_days)
        
        # 使用TimescaleDB的保留策略，不需要手动删除
        # 这里只记录日志
        logger.info("交易记录保留策略", extra={
            "retention_days": trade_retention_days,
            "trace_id": trace_id
        })
        
        # 清理已读告警
        alert_cutoff_date = datetime.utcnow() - timedelta(days=30)
        deleted_alerts = self.db.query(Alert).filter(
            Alert.is_read == True,
            Alert.create_time < alert_cutoff_date
        ).delete()
        
        self.db.commit()
        
        logger.info("已删除已读告警", extra={
            "count": deleted_alerts,
            "trace_id": trace_