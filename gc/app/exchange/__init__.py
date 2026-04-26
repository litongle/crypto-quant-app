"""
RSI分层极值追踪自动量化交易系统 - 交易所接口模块

该模块提供与各交易所API交互的统一接口，包括：
- 交易所接口的抽象基类(BaseExchange)
- 各种交易所特定的实现类(OKX, Binance, HTX等)
- 交易数据结构和枚举类型
- 交易所连接和认证管理
"""

import logging
import time
import hmac
import hashlib
import base64
import json
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Any, Optional, Union, Tuple, Callable
from datetime import datetime, timedelta
import asyncio
from urllib.parse import urlencode

import httpx
import websockets
from pydantic import BaseModel, Field, validator

from app.core.config import settings


# 配置日志
logger = logging.getLogger(__name__)


class OrderType(Enum):
    """订单类型枚举"""
    MARKET = "market"  # 市价单
    LIMIT = "limit"    # 限价单
    POST_ONLY = "post_only"  # 只做Maker单
    FOK = "fok"  # Fill or Kill
    IOC = "ioc"  # Immediate or Cancel


class OrderSide(Enum):
    """订单方向枚举"""
    BUY = "buy"        # 买入/做多
    SELL = "sell"      # 卖出/做空


class PositionSide(Enum):
    """持仓方向枚举"""
    LONG = "long"      # 多头持仓
    SHORT = "short"    # 空头持仓
    BOTH = "both"      # 双向持仓(某些交易所支持)


class OrderStatus(Enum):
    """订单状态枚举"""
    PENDING = "pending"        # 待处理
    SUBMITTED = "submitted"    # 已提交
    PARTIAL = "partial"        # 部分成交
    FILLED = "filled"          # 完全成交
    CANCELED = "canceled"      # 已取消
    REJECTED = "rejected"      # 被拒绝
    EXPIRED = "expired"        # 已过期


class MarginMode(Enum):
    """保证金模式枚举"""
    CROSS = "cross"        # 全仓模式
    ISOLATED = "isolated"  # 逐仓模式


class TimeInForce(Enum):
    """订单有效期枚举"""
    GTC = "gtc"  # Good Till Cancel，一直有效直到被取消
    IOC = "ioc"  # Immediate or Cancel，立即成交可成交的部分，剩余部分取消
    FOK = "fok"  # Fill or Kill，要么全部成交，要么全部取消
    GTX = "gtx"  # Good Till Crossing，成为Maker单前有效，否则取消


class Interval(Enum):
    """K线时间间隔枚举"""
    MIN1 = "1m"    # 1分钟
    MIN3 = "3m"    # 3分钟
    MIN5 = "5m"    # 5分钟
    MIN15 = "15m"  # 15分钟
    MIN30 = "30m"  # 30分钟
    HOUR1 = "1h"   # 1小时
    HOUR2 = "2h"   # 2小时
    HOUR4 = "4h"   # 4小时
    HOUR6 = "6h"   # 6小时
    HOUR12 = "12h" # 12小时
    DAY1 = "1d"    # 1天
    WEEK1 = "1w"   # 1周
    MONTH1 = "1M"  # 1月


class ExchangeType(Enum):
    """交易所类型枚举"""
    OKX = "okx"
    BINANCE = "binance"
    HTX = "htx"


class ApiCredential(BaseModel):
    """API凭证模型"""
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None  # OKX需要
    
    class Config:
        """配置"""
        extra = "forbid"  # 禁止额外字段


class OrderRequest(BaseModel):
    """下单请求模型"""
    symbol: str
    type: OrderType
    side: OrderSide
    price: Optional[float] = None  # 限价单需要
    amount: float
    leverage: Optional[int] = None
    margin_mode: MarginMode = MarginMode.CROSS
    position_side: Optional[PositionSide] = None
    client_order_id: Optional[str] = None
    time_in_force: Optional[TimeInForce] = None
    
    @validator('client_order_id', pre=True, always=True)
    def set_client_order_id(cls, v):
        """如果没有提供客户端订单ID，则生成一个"""
        if v is None:
            return f"RSI_{uuid.uuid4().hex[:16]}"
        return v
    
    class Config:
        """配置"""
        extra = "forbid"


class OrderResponse(BaseModel):
    """下单响应模型"""
    exchange_order_id: str
    client_order_id: str
    symbol: str
    type: OrderType
    side: OrderSide
    price: Optional[float]
    amount: float
    status: OrderStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    filled_amount: float = 0
    filled_value: float = 0
    avg_price: Optional[float] = None
    fee: Optional[float] = None
    fee_currency: Optional[str] = None
    error_message: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None
    
    class Config:
        """配置"""
        extra = "allow"  # 允许额外字段


class PositionInfo(BaseModel):
    """持仓信息模型"""
    symbol: str
    side: PositionSide
    amount: float
    entry_price: float
    mark_price: float
    liquidation_price: Optional[float] = None
    leverage: int
    margin_mode: MarginMode
    unrealized_pnl: float = 0
    realized_pnl: float = 0
    initial_margin: Optional[float] = None
    position_margin: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    raw_data: Optional[Dict[str, Any]] = None
    
    class Config:
        """配置"""
        extra = "allow"


class AccountBalance(BaseModel):
    """账户余额模型"""
    total_equity: float  # 总权益
    available_balance: float  # 可用余额
    margin_balance: float = 0  # 保证金余额
    unrealized_pnl: float = 0  # 未实现盈亏
    currency: str = "USDT"  # 货币单位
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    raw_data: Optional[Dict[str, Any]] = None
    
    class Config:
        """配置"""
        extra = "allow"


class KlineData(BaseModel):
    """K线数据模型"""
    symbol: str
    interval: str
    open_time: datetime
    close_time: Optional[datetime] = None
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: Optional[float] = None
    trades_count: Optional[int] = None
    taker_buy_volume: Optional[float] = None
    taker_buy_quote_volume: Optional[float] = None
    
    class Config:
        """配置"""
        extra = "allow"


class WebsocketMessage(BaseModel):
    """WebSocket消息模型"""
    type: str  # 消息类型
    channel: str  # 频道
    data: Dict[str, Any]  # 消息数据
    
    class Config:
        """配置"""
        extra = "allow"


class ExchangeException(Exception):
    """交易所异常基类"""
    def __init__(self, message: str, code: Optional[str] = None, http_status: Optional[int] = None, data: Any = None):
        self.message = message
        self.code = code
        self.http_status = http_status
        self.data = data
        super().__init__(self.message)


class RateLimitException(ExchangeException):
    """速率限制异常"""
    pass


class AuthenticationException(ExchangeException):
    """认证异常"""
    pass


class InsufficientFundsException(ExchangeException):
    """资金不足异常"""
    pass


class OrderException(ExchangeException):
    """订单异常"""
    pass


class NetworkException(ExchangeException):
    """网络异常"""
    pass


class BaseExchange(ABC):
    """
    交易所接口抽象基类
    
    所有具体交易所实现都应继承此类，并实现必要的抽象方法
    """
    
    def __init__(self, credentials: ApiCredential, test_mode: bool = False):
        """
        初始化交易所接口
        
        Args:
            credentials: API凭证
            test_mode: 是否使用测试模式
        """
        self.credentials = credentials
        self.test_mode = test_mode
        self.logger = logging.getLogger(f"exchange.{self.__class__.__name__.lower()}")
        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )
        self.ws_connections = {}  # WebSocket连接池
        self.ws_callbacks = {}    # WebSocket回调函数
        self.ws_tasks = {}        # WebSocket任务
        self.last_request_time = 0  # 上次请求时间，用于限速
    
    @abstractmethod
    async def get_account_balance(self) -> AccountBalance:
        """
        获取账户余额
        
        Returns:
            AccountBalance: 账户余额信息
        """
        pass
    
    @abstractmethod
    async def get_positions(self, symbol: Optional[str] = None) -> List[PositionInfo]:
        """
        获取持仓信息
        
        Args:
            symbol: 交易对，如果为None则获取所有持仓
            
        Returns:
            List[PositionInfo]: 持仓信息列表
        """
        pass
    
    @abstractmethod
    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """
        下单
        
        Args:
            order: 下单请求
            
        Returns:
            OrderResponse: 下单响应
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str, is_client_order_id: bool = False) -> bool:
        """
        取消订单
        
        Args:
            symbol: 交易对
            order_id: 订单ID
            is_client_order_id: 是否为客户端订单ID
            
        Returns:
            bool: 是否成功
        """
        pass
    
    @abstractmethod
    async def get_order(self, symbol: str, order_id: str, is_client_order_id: bool = False) -> OrderResponse:
        """
        获取订单信息
        
        Args:
            symbol: 交易对
            order_id: 订单ID
            is_client_order_id: 是否为客户端订单ID
            
        Returns:
            OrderResponse: 订单信息
        """
        pass
    
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResponse]:
        """
        获取未成交订单
        
        Args:
            symbol: 交易对，如果为None则获取所有未成交订单
            
        Returns:
            List[OrderResponse]: 未成交订单列表
        """
        pass
    
    @abstractmethod
    async def get_klines(self, symbol: str, interval: Interval, limit: int = 100, 
                        start_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> List[KlineData]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对
            interval: 时间间隔
            limit: 获取数量
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            List[KlineData]: K线数据列表
        """
        pass
    
    @abstractmethod
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        获取最新行情
        
        Args:
            symbol: 交易对
            
        Returns:
            Dict[str, Any]: 行情数据
        """
        pass
    
    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int, margin_mode: MarginMode = MarginMode.CROSS) -> bool:
        """
        设置杠杆倍数
        
        Args:
            symbol: 交易对
            leverage: 杠杆倍数
            margin_mode: 保证金模式
            
        Returns:
            bool: 是否成功
        """
        pass
    
    @abstractmethod
    async def subscribe_klines(self, symbol: str, interval: Interval, callback: Callable[[KlineData], None]) -> bool:
        """
        订阅K线数据
        
        Args:
            symbol: 交易对
            interval: 时间间隔
            callback: 回调函数
            
        Returns:
            bool: 是否成功
        """
        pass
    
    @abstractmethod
    async def subscribe_ticker(self, symbol: str, callback: Callable[[Dict[str, Any]], None]) -> bool:
        """
        订阅行情数据
        
        Args:
            symbol: 交易对
            callback: 回调函数
            
        Returns:
            bool: 是否成功
        """
        pass
    
    @abstractmethod
    async def subscribe_orders(self, callback: Callable[[OrderResponse], None]) -> bool:
        """
        订阅订单更新
        
        Args:
            callback: 回调函数
            
        Returns:
            bool: 是否成功
        """
        pass
    
    @abstractmethod
    async def subscribe_positions(self, callback: Callable[[PositionInfo], None]) -> bool:
        """
        订阅持仓更新
        
        Args:
            callback: 回调函数
            
        Returns:
            bool: 是否成功
        """
        pass
    
    @abstractmethod
    async def unsubscribe_all(self) -> bool:
        """
        取消所有订阅
        
        Returns:
            bool: 是否成功
        """
        pass
    
    async def close(self) -> None:
        """
        关闭连接
        """
        # 关闭HTTP客户端
        await self.http_client.aclose()
        
        # 关闭所有WebSocket连接
        for channel, ws in self.ws_connections.items():
            try:
                await ws.close()
                self.logger.info(f"已关闭WebSocket连接: {channel}")
            except Exception as e:
                self.logger.error(f"关闭WebSocket连接失败: {channel}, 错误: {e}")
        
        # 取消所有WebSocket任务
        for channel, task in self.ws_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                self.logger.info(f"已取消WebSocket任务: {channel}")
        
        self.logger.info(f"{self.__class__.__name__} 连接已关闭")
    
    def _generate_signature(self, data: str, secret: str) -> str:
        """
        生成签名
        
        Args:
            data: 待签名数据
            secret: 密钥
            
        Returns:
            str: 签名
        """
        return hmac.new(
            secret.encode('utf-8'),
            data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    async def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """
        处理HTTP响应
        
        Args:
            response: HTTP响应
            
        Returns:
            Dict[str, Any]: 响应数据
            
        Raises:
            ExchangeException: 交易所异常
        """
        try:
            # 记录请求和响应
            self.logger.debug(f"API请求: {response.request.method} {response.request.url}")
            self.logger.debug(f"API响应状态码: {response.status_code}")
            
            # 解析JSON响应
            data = response.json()
            
            # 检查HTTP状态码
            if response.status_code != 200:
                error_msg = data.get('msg', data.get('message', str(data)))
                error_code = data.get('code', str(response.status_code))
                
                # 根据错误类型抛出不同异常
                if response.status_code == 429:
                    raise RateLimitException(error_msg, error_code, response.status_code, data)
                elif response.status_code == 401:
                    raise AuthenticationException(error_msg, error_code, response.status_code, data)
                else:
                    raise ExchangeException(error_msg, error_code, response.status_code, data)
            
            return data
        
        except json.JSONDecodeError:
            # 非JSON响应
            self.logger.error(f"非JSON响应: {response.text}")
            raise ExchangeException(f"非JSON响应: {response.text}", http_status=response.status_code)
        
        except (RateLimitException, AuthenticationException, ExchangeException):
            # 重新抛出已处理的异常
            raise
        
        except Exception as e:
            # 其他异常
            self.logger.error(f"处理响应时发生错误: {e}")
            raise ExchangeException(f"处理响应时发生错误: {e}", http_status=response.status_code)
    
    async def _ws_connect(self, url: str, channel: str, message_handler: Callable) -> None:
        """
        建立WebSocket连接并处理消息
        
        Args:
            url: WebSocket URL
            channel: 频道名称
            message_handler: 消息处理函数
        """
        retry_count = 0
        max_retries = 10
        retry_delay = 5  # 初始重试延迟(秒)
        
        while True:
            try:
                self.logger.info(f"正在连接WebSocket: {url}, 频道: {channel}")
                
                async with websockets.connect(url) as ws:
                    self.ws_connections[channel] = ws
                    self.logger.info(f"WebSocket连接成功: {channel}")
                    
                    # 重置重试计数
                    retry_count = 0
                    retry_delay = 5
                    
                    # 处理消息
                    async for message in ws:
                        try:
                            await message_handler(message, channel)
                        except Exception as e:
                            self.logger.error(f"处理WebSocket消息时发生错误: {e}")
                    
                    # 如果连接关闭，尝试重新连接
                    self.logger.warning(f"WebSocket连接已关闭: {channel}")
            
            except (websockets.exceptions.ConnectionClosed, 
                    websockets.exceptions.ConnectionClosedError,
                    websockets.exceptions.ConnectionClosedOK) as e:
                self.logger.warning(f"WebSocket连接已关闭: {channel}, 原因: {e}")
            
            except Exception as e:
                self.logger.error(f"WebSocket连接错误: {channel}, 错误: {e}")
            
            # 检查是否应该重试
            if channel not in self.ws_callbacks:
                self.logger.info(f"已取消WebSocket订阅: {channel}")
                break
            
            # 增加重试次数
            retry_count += 1
            
            # 如果超过最大重试次数，放弃重试
            if retry_count > max_retries:
                self.logger.error(f"WebSocket连接重试次数已达上限: {channel}")
                break
            
            # 使用指数退避算法增加重试延迟
            retry_delay = min(60, retry_delay * 1.5)  # 最大延迟60秒
            
            self.logger.info(f"将在{retry_delay:.1f}秒后重试WebSocket连接: {channel}")
            await asyncio.sleep(retry_delay)
    
    def _start_ws_task(self, url: str, channel: str, message_handler: Callable) -> None:
        """
        启动WebSocket任务
        
        Args:
            url: WebSocket URL
            channel: 频道名称
            message_handler: 消息处理函数
        """
        # 如果已经有相同频道的任务，先取消它
        if channel in self.ws_tasks:
            old_task = self.ws_tasks[channel]
            if not old_task.done():
                old_task.cancel()
        
        # 创建新任务
        task = asyncio.create_task(self._ws_connect(url, channel, message_handler))
        self.ws_tasks[channel] = task
        
        # 添加完成回调
        def on_task_done(t):
            try:
                t.result()
            except asyncio.CancelledError:
                self.logger.info(f"WebSocket任务已取消: {channel}")
            except Exception as e:
                self.logger.error(f"WebSocket任务异常: {channel}, 错误: {e}")
        
        task.add_done_callback(on_task_done)


def create_exchange(exchange_type: ExchangeType, credentials: ApiCredential, test_mode: bool = False) -> BaseExchange:
    """
    创建交易所接口实例
    
    Args:
        exchange_type: 交易所类型
        credentials: API凭证
        test_mode: 是否使用测试模式
        
    Returns:
        BaseExchange: 交易所接口实例
    """
    # 导入具体实现类
    if exchange_type == ExchangeType.OKX:
        from app.exchange.okx import OKXExchange
        return OKXExchange(credentials, test_mode)
    elif exchange_type == ExchangeType.BINANCE:
        from app.exchange.binance import BinanceExchange
        return BinanceExchange(credentials, test_mode)
    elif exchange_type == ExchangeType.HTX:
        from app.exchange.htx import HTXExchange
        return HTXExchange(credentials, test_mode)
    else:
        raise ValueError(f"不支持的交易所类型: {exchange_type}")


__all__ = [
    "OrderType", "OrderSide", "PositionSide", "OrderStatus", "MarginMode",
    "TimeInForce", "Interval", "ExchangeType", "ApiCredential", "OrderRequest",
    "OrderResponse", "PositionInfo", "AccountBalance", "KlineData", "WebsocketMessage",
    "ExchangeException", "RateLimitException", "AuthenticationException",
    "InsufficientFundsException", "OrderException", "NetworkException",
    "BaseExchange", "create_exchange"
]
