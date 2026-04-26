"""
RSI分层极值追踪自动量化交易系统 - 错误处理工具类

该模块提供全面的错误处理机制，包括：
- 断路器模式 (Circuit Breaker)：防止级联故障
- 重试逻辑：处理临时性故障
- 结构化日志：提高可观测性
- 告警推送：及时通知开发团队

使用示例:
```python
# 断路器使用
from app.utils.error_handling import circuit_breaker

@circuit_breaker("okx_api")
def call_okx_api():
    # 可能失败的API调用
    pass

# 重试逻辑使用
from app.utils.error_handling import retry_with_backoff

@retry_with_backoff(max_tries=3, exceptions=(ConnectionError, TimeoutError))
def fetch_data():
    # 可能需要重试的操作
    pass

# 结构化日志使用
from app.utils.error_handling import get_logger

logger = get_logger(__name__)
logger.info("操作成功", extra={"order_id": "123", "account": "main"})

# 告警推送使用
from app.utils.error_handling import send_alert

send_alert(
    level="ERROR",
    title="订单执行失败",
    message="无法在OKX执行订单",
    details={"order_id": "123", "symbol": "ETH-USDT"}
)
```
"""

import os
import json
import time
import uuid
import logging
import functools
import threading
import traceback
import requests
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Callable, Optional, Type, Union, Set, Tuple

import pybreaker
import structlog
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential, 
    retry_if_exception_type,
    RetryError,
    before_sleep_log
)

from app.core.config import settings


# ====================== 1. 自定义异常类 ======================

class ErrorCode(Enum):
    """错误代码枚举"""
    # 系统级错误 (1000-1999)
    SYSTEM_ERROR = 1000
    CONFIG_ERROR = 1001
    DATABASE_ERROR = 1002
    REDIS_ERROR = 1003
    
    # API错误 (2000-2999)
    API_ERROR = 2000
    API_TIMEOUT = 2001
    API_RATE_LIMIT = 2002
    API_AUTHENTICATION = 2003
    
    # 业务逻辑错误 (3000-3999)
    VALIDATION_ERROR = 3000
    INSUFFICIENT_BALANCE = 3001
    ORDER_FAILED = 3002
    POSITION_NOT_FOUND = 3003
    
    # 外部依赖错误 (4000-4999)
    EXCHANGE_ERROR = 4000
    EXCHANGE_TIMEOUT = 4001
    EXCHANGE_RATE_LIMIT = 4002
    EXCHANGE_MAINTENANCE = 4003


class AppError(Exception):
    """应用自定义异常基类"""
    
    def __init__(
        self, 
        code: ErrorCode, 
        message: str, 
        details: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.trace_id = trace_id or get_trace_id()
        self.timestamp = datetime.utcnow().isoformat()
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示"""
        return {
            "code": self.code.value,
            "error_type": self.code.name,
            "message": self.message,
            "details": self.details,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp
        }
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"{self.code.name}({self.code.value}): {self.message}"


class ExchangeError(AppError):
    """交易所相关错误"""
    
    def __init__(
        self, 
        message: str, 
        exchange: str,
        code: ErrorCode = ErrorCode.EXCHANGE_ERROR, 
        details: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None
    ):
        details = details or {}
        details["exchange"] = exchange
        super().__init__(code, message, details, trace_id)


class DatabaseError(AppError):
    """数据库相关错误"""
    
    def __init__(
        self, 
        message: str, 
        code: ErrorCode = ErrorCode.DATABASE_ERROR, 
        details: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None
    ):
        super().__init__(code, message, details, trace_id)


class RedisError(AppError):
    """Redis相关错误"""
    
    def __init__(
        self, 
        message: str, 
        code: ErrorCode = ErrorCode.REDIS_ERROR, 
        details: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None
    ):
        super().__init__(code, message, details, trace_id)


# ====================== 2. 结构化日志 ======================

# 全局跟踪ID存储
_trace_id_local = threading.local()

def get_trace_id() -> str:
    """获取当前线程的跟踪ID，如果不存在则创建一个新的"""
    if not hasattr(_trace_id_local, "trace_id"):
        _trace_id_local.trace_id = str(uuid.uuid4())
    return _trace_id_local.trace_id


def set_trace_id(trace_id: str) -> None:
    """设置当前线程的跟踪ID"""
    _trace_id_local.trace_id = trace_id


def clear_trace_id() -> None:
    """清除当前线程的跟踪ID"""
    if hasattr(_trace_id_local, "trace_id"):
        delattr(_trace_id_local, "trace_id")


def add_trace_id_processor(_, __, event_dict):
    """为结构化日志添加跟踪ID"""
    if 'trace_id' not in event_dict:
        event_dict['trace_id'] = get_trace_id()
    return event_dict


def add_timestamp_processor(_, __, event_dict):
    """为结构化日志添加ISO格式时间戳"""
    event_dict['timestamp'] = datetime.utcnow().isoformat()
    return event_dict


def configure_structlog():
    """配置结构化日志"""
    processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_timestamp_processor,
        add_trace_id_processor,
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]
    
    # 根据配置选择日志格式
    if settings.LOG_FORMAT.lower() == 'json':
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def setup_logging():
    """设置日志系统"""
    # 确保日志目录存在
    os.makedirs(os.path.dirname(settings.LOG_FILE), exist_ok=True)
    
    # 配置标准库日志
    log_level = getattr(logging, settings.LOG_LEVEL)
    
    # 创建TimedRotatingFileHandler
    from logging.handlers import TimedRotatingFileHandler
    file_handler = TimedRotatingFileHandler(
        filename=settings.LOG_FILE,
        when='midnight',
        interval=1,
        backupCount=14,  # 保留14天的日志
        encoding='utf-8'
    )
    
    # 配置日志格式
    if settings.LOG_FORMAT.lower() == 'json':
        formatter = logging.Formatter('%(message)s')  # structlog会处理JSON格式
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    file_handler.setFormatter(formatter)
    
    # 配置控制台输出
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # 配置结构化日志
    configure_structlog()


def get_logger(name: str):
    """获取结构化日志器"""
    return structlog.get_logger(name)


# 创建默认日志器
logger = get_logger(__name__)


# ====================== 3. 断路器模式 ======================

# 断路器状态监听器
class CircuitBreakerListener(pybreaker.CircuitBreakerListener):
    """断路器状态变化监听器，记录日志并发送告警"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = get_logger(f"circuit_breaker.{name}")
    
    def state_change(self, cb, old_state, new_state):
        """状态变化回调"""
        self.logger.warning(
            "断路器状态变化",
            extra={
                "circuit_breaker": self.name,
                "old_state": old_state.name,
                "new_state": new_state.name,
                "failures": cb.failure_count,
            }
        )
        
        # 如果从关闭状态变为开路状态，发送告警
        if old_state.name == 'closed' and new_state.name == 'open':
            send_alert(
                level="ERROR",
                title=f"断路器触发: {self.name}",
                message=f"断路器 {self.name} 已从 {old_state.name} 变为 {new_state.name}",
                details={
                    "circuit_breaker": self.name,
                    "failures": cb.failure_count,
                    "threshold": cb.fail_max,
                    "reset_timeout": cb.reset_timeout
                }
            )
        
        # 如果恢复到关闭状态，发送恢复告警
        if old_state.name in ['open', 'half-open'] and new_state.name == 'closed':
            send_alert(
                level="INFO",
                title=f"断路器恢复: {self.name}",
                message=f"断路器 {self.name} 已从 {old_state.name} 恢复为 {new_state.name}",
                details={"circuit_breaker": self.name}
            )


# 断路器注册表
_circuit_breakers = {}

def get_circuit_breaker(name: str, fail_max: int = 5, reset_timeout: int = 30) -> pybreaker.CircuitBreaker:
    """
    获取或创建断路器
    
    Args:
        name: 断路器名称
        fail_max: 触发断路器的连续失败次数
        reset_timeout: 断路器重置超时时间(秒)
        
    Returns:
        CircuitBreaker: 断路器实例
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = pybreaker.CircuitBreaker(
            fail_max=fail_max,
            reset_timeout=reset_timeout,
            listeners=[CircuitBreakerListener(name)]
        )
    return _circuit_breakers[name]


def circuit_breaker(name: str, fail_max: int = 5, reset_timeout: int = 30):
    """
    断路器装饰器
    
    Args:
        name: 断路器名称
        fail_max: 触发断路器的连续失败次数
        reset_timeout: 断路器重置超时时间(秒)
        
    Returns:
        Callable: 装饰器函数
    """
    def decorator(func):
        breaker = get_circuit_breaker(name, fail_max, reset_timeout)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        
        return wrapper
    
    return decorator


# ====================== 4. 重试逻辑 ======================

def retry_with_backoff(
    max_tries: int = 3, 
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    min_wait: float = 0.1,
    max_wait: float = 10.0,
    jitter: bool = True
):
    """
    指数退避重试装饰器
    
    Args:
        max_tries: 最大重试次数
        exceptions: 需要重试的异常类型
        min_wait: 最小等待时间(秒)
        max_wait: 最大等待时间(秒)
        jitter: 是否添加随机抖动
        
    Returns:
        Callable: 装饰器函数
    """
    log = get_logger("retry")
    
    def decorator(func):
        @functools.wraps(func)
        @retry(
            stop=stop_after_attempt(max_tries),
            wait=wait_exponential(multiplier=min_wait, max=max_wait, exp_base=2),
            retry=retry_if_exception_type(exceptions),
            before_sleep=before_sleep_log(log, logging.WARNING),
            reraise=True
        )
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # 添加跟踪ID到异常详情
                if hasattr(e, 'details') and isinstance(e.details, dict):
                    e.details['trace_id'] = get_trace_id()
                raise
        
        return wrapper
    
    return decorator


# ====================== 5. 告警推送 ======================

class AlertLevel(Enum):
    """告警级别枚举"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def send_alert(
    level: Union[str, AlertLevel],
    title: str,
    message: str,
    details: Optional[Dict[str, Any]] = None
) -> bool:
    """
    发送告警通知
    
    Args:
        level: 告警级别
        title: 告警标题
        message: 告警消息
        details: 告警详情
        
    Returns:
        bool: 是否发送成功
    """
    if not settings.ENABLE_NOTIFICATIONS:
        # 如果未启用通知，只记录日志
        logger.warning(
            "告警通知未启用",
            extra={
                "alert_level": level if isinstance(level, str) else level.value,
                "alert_title": title,
                "alert_message": message,
                "alert_details": details
            }
        )
        return False
    
    # 标准化告警级别
    if isinstance(level, str):
        try:
            level = AlertLevel(level.upper())
        except ValueError:
            level = AlertLevel.ERROR
    
    # 准备告警数据
    alert_data = {
        "level": level.value,
        "title": title,
        "message": message,
        "details": details or {},
        "trace_id": get_trace_id(),
        "timestamp": datetime.utcnow().isoformat(),
        "hostname": os.environ.get("HOSTNAME", "unknown")
    }
    
    # 记录告警日志
    logger.warning(
        f"发送告警: {title}",
        extra={"alert": alert_data}
    )
    
    # 发送到Webhook
    if settings.NOTIFICATION_WEBHOOK:
        try:
            # 根据不同的Webhook类型，构造不同的消息格式
            webhook_url = settings.NOTIFICATION_WEBHOOK
            
            # 判断Webhook类型并格式化消息
            if "weixin" in webhook_url or "wechat" in webhook_url:
                # 企业微信格式
                payload = format_wechat_message(alert_data)
            elif "slack" in webhook_url:
                # Slack格式
                payload = format_slack_message(alert_data)
            elif "dingtalk" in webhook_url or "dingding" in webhook_url:
                # 钉钉格式
                payload = format_dingtalk_message(alert_data)
            else:
                # 通用JSON格式
                payload = alert_data
            
            # 发送请求
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=5
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"告警发送成功: {response.status_code}")
                return True
            else:
                logger.error(
                    f"告警发送失败: HTTP {response.status_code}",
                    extra={"response": response.text}
                )
                return False
                
        except Exception as e:
            logger.exception(f"发送告警通知失败: {str(e)}")
            return False
    
    # 发送邮件告警
    if settings.NOTIFICATION_EMAIL and level in [AlertLevel.ERROR, AlertLevel.CRITICAL]:
        try:
            # 这里可以实现邮件发送逻辑
            # 为简化，此处省略实现
            pass
        except Exception as e:
            logger.exception(f"发送邮件告警失败: {str(e)}")
    
    return True


def format_wechat_message(alert_data: Dict[str, Any]) -> Dict[str, Any]:
    """格式化企业微信消息"""
    level_emoji = {
        "DEBUG": "🔍",
        "INFO": "ℹ️",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "CRITICAL": "🔥"
    }
    
    emoji = level_emoji.get(alert_data["level"], "⚠️")
    
    # 构造详情文本
    details_text = ""
    if alert_data["details"]:
        for key, value in alert_data["details"].items():
            details_text += f"- {key}: {value}\n"
    
    # 构造消息内容
    content = (
        f"{emoji} **{alert_data['title']}**\n\n"
        f"{alert_data['message']}\n\n"
        f"**详情：**\n{details_text}\n"
        f"**级别：** {alert_data['level']}\n"
        f"**时间：** {alert_data['timestamp']}\n"
        f"**跟踪ID：** {alert_data['trace_id']}\n"
        f"**主机：** {alert_data['hostname']}"
    )
    
    # 企业微信格式
    return {
        "msgtype": "markdown",
        "markdown": {
            "content": content
        }
    }


def format_slack_message(alert_data: Dict[str, Any]) -> Dict[str, Any]:
    """格式化Slack消息"""
    # 根据级别设置颜色
    color_map = {
        "DEBUG": "#8A8A8A",  # 灰色
        "INFO": "#2196F3",   # 蓝色
        "WARNING": "#FFC107", # 黄色
        "ERROR": "#F44336",  # 红色
        "CRITICAL": "#9C27B0" # 紫色
    }
    
    color = color_map.get(alert_data["level"], "#F44336")
    
    # 构造字段
    fields = [
        {
            "title": "级别",
            "value": alert_data["level"],
            "short": True
        },
        {
            "title": "时间",
            "value": alert_data["timestamp"],
            "short": True
        },
        {
            "title": "主机",
            "value": alert_data["hostname"],
            "short": True
        },
        {
            "title": "跟踪ID",
            "value": alert_data["trace_id"],
            "short": True
        }
    ]
    
    # 添加详情字段
    if alert_data["details"]:
        for key, value in alert_data["details"].items():
            fields.append({
                "title": key,
                "value": str(value),
                "short": True
            })
    
    # Slack格式
    return {
        "attachments": [
            {
                "fallback": alert_data["title"],
                "color": color,
                "title": alert_data["title"],
                "text": alert_data["message"],
                "fields": fields,
                "footer": "RSI分层极值追踪量化交易系统",
                "ts": int(time.time())
            }
        ]
    }


def format_dingtalk_message(alert_data: Dict[str, Any]) -> Dict[str, Any]:
    """格式化钉钉消息"""
    level_emoji = {
        "DEBUG": "🔍",
        "INFO": "ℹ️",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "CRITICAL": "🔥"
    }
    
    emoji = level_emoji.get(alert_data["level"], "⚠️")
    
    # 构造详情文本
    details_text = ""
    if alert_data["details"]:
        for key, value in alert_data["details"].items():
            details_text += f"- {key}: {value}\n"
    
    # 构造消息内容
    content = (
        f"{emoji} **{alert_data['title']}**\n\n"
        f"{alert_data['message']}\n\n"
        f"**详情：**\n{details_text}\n"
        f"**级别：** {alert_data['level']}\n"
        f"**时间：** {alert_data['timestamp']}\n"
        f"**跟踪ID：** {alert_data['trace_id']}\n"
        f"**主机：** {alert_data['hostname']}"
    )
    
    # 钉钉格式
    return {
        "msgtype": "markdown",
        "markdown": {
            "title": f"{alert_data['level']}: {alert_data['title']}",
            "text": content
        },
        "at": {
            "isAtAll": alert_data["level"] in ["CRITICAL"]
        }
    }


# ====================== 6. 初始化 ======================

def init_error_handling():
    """初始化错误处理系统"""
    # 设置日志
    setup_logging()
    logger.info("错误处理系统初始化完成")
    
    # 注册常用断路器
    get_circuit_breaker("okx_api", fail_max=5, reset_timeout=30)
    get_circuit_breaker("database", fail_max=3, reset_timeout=10)
    get_circuit_breaker("redis", fail_max=3, reset_timeout=10)
    
    logger.info("断路器注册完成")
