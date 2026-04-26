"""
RSI分层极值追踪自动量化交易系统 - OKX交易所接口实现

该模块实现了与OKX交易所API的交互，基于OKX V5 API规范。
主要功能包括：
- 账户余额查询
- 持仓信息获取
- 订单管理（下单、查询、取消）
- K线数据获取
- 杠杆设置
- WebSocket实时数据订阅

参考文档：https://www.okx.com/docs-v5/
"""

import base64
import hmac
import hashlib
import json
import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union, Tuple, Callable
import asyncio
import logging
from urllib.parse import urlencode

import httpx
import websockets
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.exchange import (
    BaseExchange, ApiCredential, OrderRequest, OrderResponse, PositionInfo, 
    AccountBalance, KlineData, OrderType, OrderSide, PositionSide, OrderStatus, 
    MarginMode, TimeInForce, Interval, ExchangeException, RateLimitException, 
    AuthenticationException, InsufficientFundsException, OrderException, NetworkException
)
from app.core.config import settings


class OKXExchange(BaseExchange):
    """
    OKX交易所API实现
    
    基于OKX V5 API规范，提供合约交易所需的所有功能
    """
    
    # API端点
    API_URL = "https://www.okx.com"
    WS_PUBLIC_URL = "wss://ws.okx.com:8443/ws/v5/public"
    WS_PRIVATE_URL = "wss://ws.okx.com:8443/ws/v5/private"
    
    # 测试网API端点
    TESTNET_API_URL = "https://www.okx.com/api/v5/mock"
    TESTNET_WS_PUBLIC_URL = "wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999"
    TESTNET_WS_PRIVATE_URL = "wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999"
    
    # API请求速率限制（每秒请求数）
    RATE_LIMIT = 6
    
    def __init__(self, credentials: ApiCredential, test_mode: bool = False):
        """
        初始化OKX交易所接口
        
        Args:
            credentials: API凭证
            test_mode: 是否使用测试模式
        """
        super().__init__(credentials, test_mode)
        
        # 设置API URL
        if test_mode:
            self.api_url = self.TESTNET_API_URL
            self.ws_public_url = self.TESTNET_WS_PUBLIC_URL
            self.ws_private_url = self.TESTNET_WS_PRIVATE_URL
        else:
            self.api_url = settings.OKX_API_URL or self.API_URL
            self.ws_public_url = settings.OKX_WS_PUBLIC_URL or self.WS_PUBLIC_URL
            self.ws_private_url = settings.OKX_WS_PRIVATE_URL or self.WS_PRIVATE_URL
        
        self.logger = logging.getLogger("exchange.okx")
        self.logger.info(f"OKX交易所接口初始化完成, 测试模式: {test_mode}")
    
    def _get_timestamp(self) -> str:
        """
        获取ISO格式的时间戳
        
        Returns:
            str: ISO格式的时间戳
        """
        return datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'
    
    def _sign_request(self, method: str, request_path: str, body: str = '') -> Tuple[str, str, str]:
        """
        生成OKX API请求签名
        
        Args:
            method: 请求方法（GET/POST/DELETE等）
            request_path: 请求路径
            body: 请求体（JSON字符串）
            
        Returns:
            Tuple[str, str, str]: (时间戳, 签名, 签名方法)
        """
        # 获取时间戳
        timestamp = self._get_timestamp()
        
        # 构造待签名字符串
        message = timestamp + method + request_path
        if body:
            message += body
        
        # 使用API密钥进行HMAC-SHA256签名
        mac = hmac.new(
            bytes(self.credentials.api_secret, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        signature = base64.b64encode(mac.digest()).decode('utf-8')
        
        return timestamp, signature, '2'  # 签名方法2
    
    def _get_headers(self, method: str, request_path: str, body: str = '') -> Dict[str, str]:
        """
        获取API请求头
        
        Args:
            method: 请求方法（GET/POST/DELETE等）
            request_path: 请求路径
            body: 请求体（JSON字符串）
            
        Returns:
            Dict[str, str]: 请求头
        """
        timestamp, signature, sign_method = self._sign_request(method, request_path, body)
        
        return {
            'OK-ACCESS-KEY': self.credentials.api_key,
            'OK-ACCESS-SIGN': signature,
            'OK-ACCESS-TIMESTAMP': timestamp,
            'OK-ACCESS-PASSPHRASE': self.credentials.passphrase,
            'Content-Type': 'application/json',
            'x-simulated-trading': '1' if self.test_mode else '0'
        }
    
    async def _request(self, method: str, endpoint: str, params: Dict[str, Any] = None, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        发送API请求
        
        Args:
            method: 请求方法（GET/POST/DELETE等）
            endpoint: API端点
            params: URL参数
            data: 请求体数据
            
        Returns:
            Dict[str, Any]: 响应数据
            
        Raises:
            ExchangeException: 交易所异常
        """
        # 构造请求URL
        url = f"{self.api_url}{endpoint}"
        
        # 构造请求路径（用于签名）
        request_path = endpoint
        if params:
            query_string = urlencode(params)
            url = f"{url}?{query_string}"
            request_path = f"{endpoint}?{query_string}"
        
        # 构造请求体
        body = ''
        if data:
            body = json.dumps(data)
        
        # 获取请求头
        headers = self._get_headers(method, request_path, body)
        
        # 实现限速
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < 1.0 / self.RATE_LIMIT:
            await asyncio.sleep(1.0 / self.RATE_LIMIT - elapsed)
        
        # 记录请求
        self.last_request_time = time.time()
        self.logger.debug(f"发送{method}请求: {url}")
        if data:
            self.logger.debug(f"请求数据: {json.dumps(data)}")
        
        try:
            # 发送请求
            response = await self.http_client.request(
                method=method,
                url=url,
                headers=headers,
                json=data if data else None,
                timeout=30.0
            )
            
            # 处理响应
            result = await self._handle_response(response)
            
            # 检查OKX API错误
            if result.get('code') != '0':
                error_msg = result.get('msg', 'Unknown error')
                error_code = result.get('code', 'unknown')
                
                # 根据错误代码抛出不同异常
                if error_code in ('50111', '50112'):  # 资金不足
                    raise InsufficientFundsException(error_msg, error_code)
                elif error_code in ('50001', '50002'):  # 参数错误
                    raise OrderException(error_msg, error_code)
                elif error_code in ('50004', '50005'):  # 频率限制
                    raise RateLimitException(error_msg, error_code)
                elif error_code in ('50006', '50007', '50008'):  # 认证错误
                    raise AuthenticationException(error_msg, error_code)
                else:
                    raise ExchangeException(error_msg, error_code)
            
            return result.get('data', {})
            
        except httpx.RequestError as e:
            self.logger.error(f"HTTP请求错误: {e}")
            raise NetworkException(f"HTTP请求错误: {e}")
        
        except (RateLimitException, AuthenticationException, 
                InsufficientFundsException, OrderException, ExchangeException):
            # 重新抛出已处理的异常
            raise
        
        except Exception as e:
            self.logger.error(f"请求处理错误: {e}")
            raise ExchangeException(f"请求处理错误: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(NetworkException)
    )
    async def get_account_balance(self) -> AccountBalance:
        """
        获取账户余额
        
        Returns:
            AccountBalance: 账户余额信息
        """
        try:
            # 获取账户余额
            result = await self._request('GET', '/api/v5/account/balance')
            
            if not result or not isinstance(result, list) or len(result) == 0:
                raise ExchangeException("获取账户余额失败: 无效响应")
            
            # 获取USDT余额
            usdt_balance = None
            for item in result[0].get('details', []):
                if item.get('ccy') == 'USDT':
                    usdt_balance = item
                    break
            
            if not usdt_balance:
                self.logger.warning("未找到USDT余额，返回总账户余额")
                # 使用总账户余额
                return AccountBalance(
                    total_equity=float(result[0].get('totalEq', '0')),
                    available_balance=float(result[0].get('availEq', '0')),
                    margin_balance=float(result[0].get('imr', '0')),
                    unrealized_pnl=float(result[0].get('upl', '0')),
                    currency="USDT",
                    updated_at=datetime.utcnow(),
                    raw_data=result
                )
            
            # 返回USDT余额
            return AccountBalance(
                total_equity=float(usdt_balance.get('eq', '0')),
                available_balance=float(usdt_balance.get('availEq', '0')),
                margin_balance=float(usdt_balance.get('frozenBal', '0')),
                unrealized_pnl=float(usdt_balance.get('upl', '0')),
                currency="USDT",
                updated_at=datetime.utcnow(),
                raw_data=usdt_balance
            )
            
        except (RateLimitException, AuthenticationException, ExchangeException) as e:
            self.logger.error(f"获取账户余额失败: {e}")
            raise
        
        except Exception as e:
            self.logger.error(f"获取账户余额时发生未知错误: {e}")
            raise ExchangeException(f"获取账户余额时发生未知错误: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(NetworkException)
    )
    async def get_positions(self, symbol: Optional[str] = None) -> List[PositionInfo]:
        """
        获取持仓信息
        
        Args:
            symbol: 交易对，如果为None则获取所有持仓
            
        Returns:
            List[PositionInfo]: 持仓信息列表
        """
        try:
            # 构造请求参数
            params = {}
            if symbol:
                params['instId'] = symbol
            
            # 获取持仓信息
            result = await self._request('GET', '/api/v5/account/positions', params=params)
            
            if not result:
                return []
            
            positions = []
            for pos in result:
                # 确定持仓方向
                side = PositionSide.LONG if pos.get('posSide') == 'long' else PositionSide.SHORT
                
                # 确定保证金模式
                margin_mode = MarginMode.CROSS if pos.get('mgnMode') == 'cross' else MarginMode.ISOLATED
                
                # 创建持仓信息对象
                position = PositionInfo(
                    symbol=pos.get('instId', ''),
                    side=side,
                    amount=float(pos.get('pos', '0')),
                    entry_price=float(pos.get('avgPx', '0')),
                    mark_price=float(pos.get('markPx', '0')),
                    liquidation_price=float(pos.get('liqPx', '0')) if pos.get('liqPx') else None,
                    leverage=int(pos.get('lever', '1')),
                    margin_mode=margin_mode,
                    unrealized_pnl=float(pos.get('upl', '0')),
                    realized_pnl=float(pos.get('realizedPnl', '0')),
                    initial_margin=float(pos.get('imr', '0')),
                    position_margin=float(pos.get('margin', '0')),
                    created_at=datetime.fromtimestamp(int(pos.get('cTime', '0')) / 1000) if pos.get('cTime') else None,
                    updated_at=datetime.fromtimestamp(int(pos.get('uTime', '0')) / 1000) if pos.get('uTime') else None,
                    raw_data=pos
                )
                positions.append(position)
            
            return positions
            
        except (RateLimitException, AuthenticationException, ExchangeException) as e:
            self.logger.error(f"获取持仓信息失败: {e}")
            raise
        
        except Exception as e:
            self.logger.error(f"获取持仓信息时发生未知错误: {e}")
            raise ExchangeException(f"获取持仓信息时发生未知错误: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(NetworkException)
    )
    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """
        下单
        
        Args:
            order: 下单请求
            
        Returns:
            OrderResponse: 下单响应
        """
        try:
            # 确定交易方向和持仓方向
            side, pos_side = self._convert_order_side(order.side, order.position_side)
            
            # 构造请求数据
            data = {
                'instId': order.symbol,
                'tdMode': order.margin_mode.value,  # 交易模式: cross(全仓), isolated(逐仓)
                'side': side,  # buy, sell
                'ordType': self._convert_order_type(order.type),  # market, limit, post_only, fok, ioc
                'sz': str(order.amount),  # 委托数量
                'clOrdId': order.client_order_id,  # 客户端订单ID
            }
            
            # 如果是限价单，添加价格
            if order.type != OrderType.MARKET and order.price is not None:
                data['px'] = str(order.price)
            
            # 如果指定了持仓方向，添加持仓方向
            if pos_side:
                data['posSide'] = pos_side  # long, short
            
            # 如果指定了有效期，添加有效期
            if order.time_in_force:
                data['tgtCcy'] = self._convert_time_in_force(order.time_in_force)
            
            # 发送下单请求
            result = await self._request('POST', '/api/v5/trade/order', data=data)
            
            if not result or not isinstance(result, list) or len(result) == 0:
                raise OrderException("下单失败: 无效响应")
            
            order_info = result[0]
            
            # 检查下单结果
            if order_info.get('sCode') != '0':
                error_msg = order_info.get('sMsg', 'Unknown error')
                raise OrderException(f"下单失败: {error_msg}")
            
            # 构造下单响应
            response = OrderResponse(
                exchange_order_id=order_info.get('ordId', ''),
                client_order_id=order_info.get('clOrdId', order.client_order_id),
                symbol=order.symbol,
                type=order.type,
                side=order.side,
                price=order.price,
                amount=order.amount,
                status=self._convert_order_status(order_info.get('state', '')),
                created_at=datetime.utcnow(),
                filled_amount=0,
                filled_value=0,
                raw_response=order_info
            )
            
            return response
            
        except (RateLimitException, AuthenticationException, 
                InsufficientFundsException, OrderException, ExchangeException) as e:
            self.logger.error(f"下单失败: {e}")
            raise
        
        except Exception as e:
            self.logger.error(f"下单时发生未知错误: {e}")
            raise ExchangeException(f"下单时发生未知错误: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(NetworkException)
    )
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
        try:
            # 构造请求数据
            data = {
                'instId': symbol,
            }
            
            # 根据ID类型设置参数
            if is_client_order_id:
                data['clOrdId'] = order_id
            else:
                data['ordId'] = order_id
            
            # 发送取消订单请求
            result = await self._request('POST', '/api/v5/trade/cancel-order', data=data)
            
            if not result or not isinstance(result, list) or len(result) == 0:
                raise OrderException("取消订单失败: 无效响应")
            
            cancel_info = result[0]
            
            # 检查取消结果
            if cancel_info.get('sCode') != '0':
                error_msg = cancel_info.get('sMsg', 'Unknown error')
                raise OrderException(f"取消订单失败: {error_msg}")
            
            return True
            
        except (RateLimitException, AuthenticationException, OrderException, ExchangeException) as e:
            self.logger.error(f"取消订单失败: {e}")
            raise
        
        except Exception as e:
            self.logger.error(f"取消订单时发生未知错误: {e}")
            raise ExchangeException(f"取消订单时发生未知错误: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(NetworkException)
    )
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
        try:
            # 构造请求参数
            params = {
                'instId': symbol,
            }
            
            # 根据ID类型设置参数
            if is_client_order_id:
                params['clOrdId'] = order_id
            else:
                params['ordId'] = order_id
            
            # 发送获取订单请求
            result = await self._request('GET', '/api/v5/trade/order', params=params)
            
            if not result or not isinstance(result, list) or len(result) == 0:
                raise OrderException("获取订单信息失败: 无效响应")
            
            order_info = result[0]
            
            # 解析订单信息
            order_type = self._parse_order_type(order_info.get('ordType', ''))
            order_side = self._parse_order_side(order_info.get('side', ''), order_info.get('posSide', ''))
            
            # 构造订单响应
            response = OrderResponse(
                exchange_order_id=order_info.get('ordId', ''),
                client_order_id=order_info.get('clOrdId', ''),
                symbol=order_info.get('instId', symbol),
                type=order_type,
                side=order_side,
                price=float(order_info.get('px', '0')) if order_info.get('px') else None,
                amount=float(order_info.get('sz', '0')),
                status=self._convert_order_status(order_info.get('state', '')),
                created_at=datetime.fromtimestamp(int(order_info.get('cTime', '0')) / 1000) if order_info.get('cTime') else datetime.utcnow(),
                updated_at=datetime.fromtimestamp(int(order_info.get('uTime', '0')) / 1000) if order_info.get('uTime') else None,
                filled_amount=float(order_info.get('accFillSz', '0')),
                filled_value=float(order_info.get('fillPx', '0')) * float(order_info.get('accFillSz', '0')),
                avg_price=float(order_info.get('avgPx', '0')) if order_info.get('avgPx') else None,
                fee=float(order_info.get('fee', '0')),
                fee_currency=order_info.get('feeCcy', ''),
                raw_response=order_info
            )
            
            return response
            
        except (RateLimitException, AuthenticationException, OrderException, ExchangeException) as e:
            self.logger.error(f"获取订单信息失败: {e}")
            raise
        
        except Exception as e:
            self.logger.error(f"获取订单信息时发生未知错误: {e}")
            raise ExchangeException(f"获取订单信息时发生未知错误: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(NetworkException)
    )
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResponse]:
        """
        获取未成交订单
        
        Args:
            symbol: 交易对，如果为None则获取所有未成交订单
            
        Returns:
            List[OrderResponse]: 未成交订单列表
        """
        try:
            # 构造请求参数
            params = {
                'state': 'live'  # 活跃订单
            }
            
            if symbol:
                params['instId'] = symbol
            
            # 发送获取未成交订单请求
            result = await self._request('GET', '/api/v5/trade/orders-pending', params=params)
            
            if not result:
                return []
            
            orders = []
            for order_info in result:
                # 解析订单信息
                order_type = self._parse_order_type(order_info.get('ordType', ''))
                order_side = self._parse_order_side(order_info.get('side', ''), order_info.get('posSide', ''))
                
                # 构造订单响应
                response = OrderResponse(
                    exchange_order_id=order_info.get('ordId', ''),
                    client_order_id=order_info.get('clOrdId', ''),
                    symbol=order_info.get('instId', ''),
                    type=order_type,
                    side=order_side,
                    price=float(order_info.get('px', '0')) if order_info.get('px') else None,
                    amount=float(order_info.get('sz', '0')),
                    status=self._convert_order_status(order_info.get('state', '')),
                    created_at=datetime.fromtimestamp(int(order_info.get('cTime', '0')) / 1000) if order_info.get('cTime') else datetime.utcnow(),
                    updated_at=datetime.fromtimestamp(int(order_info.get('uTime', '0')) / 1000) if order_info.get('uTime') else None,
                    filled_amount=float(order_info.get('accFillSz', '0')),
                    filled_value=float(order_info.get('fillPx', '0')) * float(order_info.get('accFillSz', '0')),
                    avg_price=float(order_info.get('avgPx', '0')) if order_info.get('avgPx') else None,
                    fee=float(order_info.get('fee', '0')),
                    fee_currency=order_info.get('feeCcy', ''),
                    raw_response=order_info
                )
                orders.append(response)
            
            return orders
            
        except (RateLimitException, AuthenticationException, ExchangeException) as e:
            self.logger.error(f"获取未成交订单失败: {e}")
            raise
        
        except Exception as e:
            self.logger.error(f"获取未成交订单时发生未知错误: {e}")
            raise ExchangeException(f"获取未成交订单时发生未知错误: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(NetworkException)
    )
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
        try:
            # 转换时间间隔
            bar = self._convert_interval(interval)
            
            # 构造请求参数
            params = {
                'instId': symbol,
                'bar': bar,
                'limit': str(min(limit, 100))  # OKX API限制最多返回100条
            }
            
            # 添加开始时间和结束时间
            if start_time:
                params['before'] = str(int(start_time.timestamp() * 1000))
            if end_time:
                params['after'] = str(int(end_time.timestamp() * 1000))
            
            # 发送获取K线数据请求
            result = await self._request('GET', '/api/v5/market/candles', params=params)
            
            if not result:
                return []
            
            klines = []
            for k in result:
                # OKX K线数据格式: [timestamp, open, high, low, close, volume, ...]
                if len(k) < 6:
                    continue
                
                timestamp = int(k[0])
                open_time = datetime.fromtimestamp(timestamp / 1000)
                
                # 计算收盘时间
                interval_seconds = self._interval_to_seconds(interval)
                close_time = open_time + timedelta(seconds=interval_seconds)
                
                # 构造K线数据
                kline = KlineData(
                    symbol=symbol,
                    interval=interval.value,
                    open_time=open_time,
                    close_time=close_time,
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5]),
                    quote_volume=float(k[6]) if len(k) > 6 else None,
                    trades_count=None  # OKX API不提供成交笔数
                )
                klines.append(kline)
            
            # 按时间排序
            klines.sort(key=lambda x: x.open_time)
            
            return klines
            
        except (RateLimitException, AuthenticationException, ExchangeException) as e:
            self.logger.error(f"获取K线数据失败: {e}")
            raise
        
        except Exception as e:
            self.logger.error(f"获取K线数据时发生未知错误: {e}")
            raise ExchangeException(f"获取K线数据时发生未知错误: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(NetworkException)
    )
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        获取最新行情
        
        Args:
            symbol: 交易对
            
        Returns:
            Dict[str, Any]: 行情数据
        """
        try:
            # 构造请求参数
            params = {
                'instId': symbol
            }
            
            # 发送获取行情请求
            result = await self._request('GET', '/api/v5/market/ticker', params=params)
            
            if not result or not isinstance(result, list) or len(result) == 0:
                raise ExchangeException("获取行情失败: 无效响应")
            
            ticker = result[0]
            
            # 构造行情数据
            return {
                'symbol': symbol,
                'last': float(ticker.get('last', '0')),
                'high_24h': float(ticker.get('high24h', '0')),
                'low_24h': float(ticker.get('low24h', '0')),
                'volume_24h': float(ticker.get('vol24h', '0')),
                'quote_volume_24h': float(ticker.get('volCcy24h', '0')),
                'open_24h': float(ticker.get('open24h', '0')),
                'price_change_24h': float(ticker.get('last', '0')) - float(ticker.get('open24h', '0')),
                'price_change_percent_24h': (float(ticker.get('last', '0')) - float(ticker.get('open24h', '0'))) / float(ticker.get('open24h', '1')) * 100 if float(ticker.get('open24h', '0')) != 0 else 0,
                'bid': float(ticker.get('bidPx', '0')),
                'ask': float(ticker.get('askPx', '0')),
                'timestamp': datetime.fromtimestamp(int(ticker.get('ts', '0')) / 1000) if ticker.get('ts') else datetime.utcnow(),
                'raw_data': ticker
            }
            
        except (RateLimitException, AuthenticationException, ExchangeException) as e:
            self.logger.error(f"获取行情失败: {e}")
            raise
        
        except Exception as e:
            self.logger.error(f"获取行情时发生未知错误: {e}")
            raise ExchangeException(f"获取行情时发生未知错误: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(NetworkException)
    )
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
        try:
            # 构造请求数据
            data = {
                'instId': symbol,
                'lever': str(leverage),
                'mgnMode': margin_mode.value
            }
            
            # 发送设置杠杆倍数请求
            result = await self._request('POST', '/api/v5/account/set-leverage', data=data)
            
            if not result or not isinstance(result, list) or len(result) == 0:
                raise ExchangeException("设置杠杆倍数失败: 无效响应")
            
            leverage_info = result[0]
            
            # 检查设置结果
            if leverage_info.get('instId') == symbol and leverage_info.get('lever') == str(leverage):
                self.logger.info(f"设置杠杆倍数成功: {symbol} {leverage}倍 {margin_mode.value}模式")
                return True
            else:
                raise ExchangeException(f"设置杠杆倍数失败: {leverage_info}")
            
        except (RateLimitException, AuthenticationException, ExchangeException) as e:
            self.logger.error(f"设置杠杆倍数失败: {e}")
            raise
        
        except Exception as e:
            self.logger.error(f"设置杠杆倍数时发生未知错误: {e}")
            raise ExchangeException(f"设置杠杆倍数时发生未知错误: {e}")
    
    async def _ws_login(self, ws: websockets.WebSocketClientProtocol) -> bool:
        """
        WebSocket登录
        
        Args:
            ws: WebSocket连接
            
        Returns:
            bool: 是否登录成功
        """
        try:
            # 获取时间戳
            timestamp = self._get_timestamp()
            
            # 构造签名
            message = timestamp + 'GET' + '/users/self/verify'
            signature = hmac.new(
                bytes(self.credentials.api_secret, encoding='utf8'),
                bytes(message, encoding='utf-8'),
                digestmod='sha256'
            ).hexdigest()
            
            # 构造登录请求
            login_request = {
                'op': 'login',
                'args': [
                    {
                        'apiKey': self.credentials.api_key,
                        'passphrase': self.credentials.passphrase,
                        'timestamp': timestamp,
                        'sign': signature
                    }
                ]
            }
            
            # 发送登录请求
            await ws.send(json.dumps(login_request))
            
            # 等待登录响应
            response = await asyncio.wait_for(ws.recv(), timeout=10)
            response_data = json.loads(response)
            
            # 检查登录结果
            if response_data.get('event') == 'login' and response_data.get('code') == '0':
                self.logger.info("WebSocket登录成功")
                return True
            else:
                self.logger.error(f"WebSocket登录失败: {response_data}")
                return False
            
        except Exception as e:
            self.logger.error(f"WebSocket登录时发生错误: {e}")
            return False
    
    async def _ws_message_handler(self, message: str, channel: str) -> None:
        """
        处理WebSocket消息
        
        Args:
            message: 消息内容
            channel: 频道名称
        """
        try:
            # 解析消息
            data = json.loads(message)
            
            # 处理ping消息
            if 'event' in data and data['event'] == 'ping':
                # 发送pong响应
                if channel in self.ws_connections:
                    pong = {'op': 'pong'}
                    await self.ws_connections[channel].send(json.dumps(pong))
                return
            
            # 处理订阅确认
            if 'event' in data and data['event'] == 'subscribe':
                self.logger.info(f"订阅成功: {data.get('arg', {})}")
                return
            
            # 处理错误消息
            if 'event' in data and data['event'] == 'error':
                self.logger.error(f"WebSocket错误: {data}")
                return
            
            # 处理数据消息
            if 'data' in data:
                # 获取回调函数
                callback = self.ws_callbacks.get(channel)
                if callback:
                    # 调用回调函数处理数据
                    for item in data['data']:
                        await callback(item)
            
        except json.JSONDecodeError:
            self.logger.error(f"解析WebSocket消息失败: {message}")
        
        except Exception as e:
            self.logger.error(f"处理WebSocket消息时发生错误: {e}")
    
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
        try:
            # 转换时间间隔
            bar = self._convert_interval(interval)
            
            # 构造频道名称
            channel = f"candle{bar}:{symbol}"
            
            # 构造订阅请求
            subscribe_request = {
                'op': 'subscribe',
                'args': [
                    {
                        'channel': f"candle{bar}",
                        'instId': symbol
                    }
                ]
            }
            
            # 定义回调函数
            async def kline_callback(data: Dict[str, Any]) -> None:
                try:
                    # 解析K线数据
                    if not isinstance(data, list) or len(data) < 6:
                        return
                    
                    timestamp = int(data[0])
                    open_time = datetime.fromtimestamp(timestamp / 1000)
                    
                    # 计算收盘时间
                    interval_seconds = self._interval_to_seconds(interval)
                    close_time = open_time + timedelta(seconds=interval_seconds)
                    
                    # 构造K线数据
                    kline = KlineData(
                        symbol=symbol,
                        interval=interval.value,
                        open_time=open_time,
                        close_time=close_time,
                        open=float(data[1]),
                        high=float(data[2]),
                        low=float(data[3]),
                        close=float(data[4]),
                        volume=float(data[5]),
                        quote_volume=float(data[6]) if len(data) > 6 else None,
                        trades_count=None  # OKX API不提供成交笔数
                    )
                    
                    # 调用用户回调函数
                    await callback(kline)
                    
                except Exception as e:
                    self.logger.error(f"处理K线数据时发生错误: {e}")
            
            # 保存回调函数
            self.ws_callbacks[channel] = kline_callback
            
            # 启动WebSocket任务
            self._start_ws_task(
                url=self.ws_public_url,
                channel=channel,
                message_handler=self._ws_message_handler
            )
            
            # 等待连接建立
            await asyncio.sleep(1)
            
            # 发送订阅请求
            if channel in self.ws_connections:
                await self.ws_connections[channel].send(json.dumps(subscribe_request))
                self.logger.info(f"已订阅K线数据: {symbol} {interval.value}")
                return True
            else:
                self.logger.error(f"订阅K线数据失败: 无法建立WebSocket连接")
                return False
            
        except Exception as e:
            self.logger.error(f"订阅K线数据时发生错误: {e}")
            return False
    
    async def subscribe_ticker(self, symbol: str, callback: Callable[[Dict[str, Any]], None]) -> bool:
        """
        订阅行情数据
        
        Args:
            symbol: 交易对
            callback: 回调函数
            
        Returns:
            bool: 是否成功
        """
        try:
            # 构造频道名称
            channel = f"tickers:{symbol}"
            
            # 构造订阅请求
            subscribe_request = {
                'op': 'subscribe',
                'args': [
                    {
                        'channel': 'tickers',
                        'instId': symbol
                    }
                ]
            }
            
            # 定义回调函数
            async def ticker_callback(data: Dict[str, Any]) -> None:
                try:
                    # 构造行情数据
                    ticker = {
                        'symbol': symbol,
                        'last': float(data.get('last', '0')),
                        'high_24h': float(data.get('high24h', '0')),
                        'low_24h': float(data.get('low24h', '0')),
                        'volume_24h': float(data.get('vol24h', '0')),
                        'quote_volume_24h': float(data.get('volCcy24h', '0')),
                        'open_24h': float(data.get('open24h', '0')),
                        'price_change_24h': float(data.get('last', '0')) - float(data.get('open24h', '0')),
                        'price_change_percent_24h': (float(data.get('last', '0')) - float(data.get('open24h', '0'))) / float(data.get('open24h', '1')) * 100 if float(data.get('open24h', '0')) != 0 else 0,
                        'bid': float(data.get('bidPx', '0')),
                        'ask': float(data.get('askPx', '0')),
                        'timestamp': datetime.fromtimestamp(int(data.get('ts', '0')) / 1000) if data.get('ts') else datetime.utcnow(),
                        'raw_data': data
                    }
                    
                    # 调用用户回调函数
                    await callback(ticker)
                    
                except Exception as e:
                    self.logger.error(f"处理行情数据时发生错误: {e}")
            
            # 保存回调函数
            self.ws_callbacks[channel] = ticker_callback
            
            # 启动WebSocket任务
            self._start_ws_task(
                url=self.ws_public_url,
                channel=channel,
                message_handler=self._ws_message_handler
            )
            
            # 等待连接建立
            await asyncio.sleep(1)
            
            # 发送订阅请求
            if channel in self.ws_connections:
                await self.ws_connections[channel].send(json.dumps(subscribe_request))
                self.logger.info(f"已订阅行情数据: {symbol}")
                return True
            else:
                self.logger.error(f"订阅行情数据失败: 无法建立WebSocket连接")
                return False
            
        except Exception as e:
            self.logger.error(f"订阅行情数据时发生错误: {e}")
            return False
    
    async def subscribe_orders(self, callback: Callable[[OrderResponse], None]) -> bool:
        """
        订阅订单更新
        
        Args:
            callback: 回调函数
            
        Returns:
            bool: 是否成功
        """
        try:
            # 构造频道名称
            channel = "orders"
            
            # 构造订阅请求
            subscribe_request = {
                'op': 'subscribe',
                'args': [
                    {
                        'channel': 'orders',
                        'instType': 'SWAP'  # 只订阅永续合约
                    }
                ]
            }
            
            # 定义回调函数
            async def order_callback(data: Dict[str, Any]) -> None:
                try:
                    # 解析订单信息
                    order_type = self._parse_order_type(data.get('ordType', ''))
                    order_side = self._parse_order_side(data.get('side', ''), data.get('posSide', ''))
                    
                    # 构造订单响应
                    order = OrderResponse(
                        exchange_order_id=data.get('ordId', ''),
                        client_order_id=data.get('clOrdId', ''),
                        symbol=data.get('instId', ''),
                        type=order_type,
                        side=order_side,
                        price=float(data.get('px', '0')) if data.get('px') else None,
                        amount=float(data.get('sz', '0')),
                        status=self._convert_order_status(data.get('state', '')),
                        created_at=datetime.fromtimestamp(int(data.get('cTime', '0')) / 1000) if data.get('cTime') else datetime.utcnow(),
                        updated_at=datetime.fromtimestamp(int(data.get('uTime', '0')) / 1000) if data.get('uTime') else None,
                        filled_amount=float(data.get('accFillSz', '0')),
                        filled_value=float(data.get('fillPx', '0')) * float(data.get('accFillSz', '0')),
                        avg_price=float(data.get('avgPx', '0')) if data.get('avgPx') else None,
                        fee=float(data.get('fee', '0')),
                        fee_currency=data.get('feeCcy', ''),
                        raw_response=data
                    )
                    
                    # 调用用户回调函数
                    await callback(order)
                    
                except Exception as e:
                    self.logger.error(f"处理订单更新时发生错误: {e}")
            
            # 保存回调函数
            self.ws_callbacks[channel] = order_callback
            
            # 启动WebSocket任务
            self._start_ws_task(
                url=self.ws_private_url,
                channel=channel,
                message_handler=self._ws_message_handler
            )
            
            # 等待连接建立
            await asyncio.sleep(1)
            
            # 登录WebSocket
            if channel in self.ws_connections:
                if await self._ws_login(self.ws_connections[channel]):
                    # 发送订阅请求
                    await self.ws_connections[channel].send(json.dumps(subscribe_request))
                    self.logger.info("已订阅订单更新")
                    return True
                else:
                    self.logger.error("订阅订单更新失败: WebSocket登录失败")
                    return False
            else:
                self.logger.error("订阅订单更新失败: 无法建立WebSocket连接")
                return False
            
        except Exception as e:
            self.logger.error(f"订阅订单更新时发生错误: {e}")
            return False
    
    async def subscribe_positions(self, callback: Callable[[PositionInfo], None]) -> bool:
        """
        订阅持仓更新
        
        Args:
            callback: 回调函数
            
        Returns:
            bool: 是否成功
        """
        try:
            # 构造频道名称
            channel = "positions"
            
            # 构造订阅请求
            subscribe_request = {
                'op': 'subscribe',
                'args': [
                    {
                        'channel': 'positions',
                        'instType': 'SWAP'  # 只订阅永续合约
                    }
                ]
            }
            
            # 定义回调函数
            async def position_callback(data: Dict[str, Any]) -> None:
                try:
                    # 确定持仓方向
                    side = PositionSide.LONG if data.get('posSide') == 'long' else PositionSide.SHORT
                    
                    # 确定保证金模式
                    margin_mode = MarginMode.CROSS if data.get('mgnMode') == 'cross' else MarginMode.ISOLATED
                    
                    # 构造持仓信息
                    position = PositionInfo(
                        symbol=data.get('instId', ''),
                        side=side,
                        amount=float(data.get('pos', '0')),
                        entry_price=float(data.get('avgPx', '0')),
                        mark_price=float(data.get('markPx', '0')),
                        liquidation_price=float(data.get('liqPx', '0')) if data.get('liqPx') else None,
                        leverage=int(data.get('lever', '1')),
                        margin_mode=margin_mode,
                        unrealized_pnl=float(data.get('upl', '0')),
                        realized_pnl=float(data.get('realizedPnl', '0')),
                        initial_margin=float(data.get('imr', '0')),
                        position_margin=float(data.get('margin', '0')),
                        created_at=datetime.fromtimestamp(int(data.get('cTime', '0')) / 1000) if data.get('cTime') else None,
                        updated_at=datetime.fromtimestamp(int(data.get('uTime', '0')) / 1000) if data.get('uTime') else None,
                        raw_data=data
                    )
                    
                    # 调用用户回调函数
                    await callback(position)
                    
                except Exception as e:
                    self.logger.error(f"处理持仓更新时发生错误: {e}")
            
            # 保存回调函数
            self.ws_callbacks[channel] = position_callback
            
            # 启动WebSocket任务
            self._start_ws_task(
                url=self.ws_private_url,
                channel=channel,
                message_handler=self._ws_message_handler
            )
            
            # 等待连接建立
            await asyncio.sleep(1)
            
            # 登录WebSocket
            if channel in self.ws_connections:
                if await self._ws_login(self.ws_connections[channel]):
                    # 发送订阅请求
                    await self.ws_connections[channel].send(json.dumps(subscribe_request))
                    self.logger.info("已订阅持仓更新")
                    return True
                else:
                    self.logger.error("订阅持仓更新失败: WebSocket登录失败")
                    return False
            else:
                self.logger.error("订阅持仓更新失败: 无法建立WebSocket连接")
                return False
            
        except Exception as e:
            self.logger.error(f"订阅持仓更新时发生错误: {e}")
            return False
    
    async def unsubscribe_all(self) -> bool:
        """
        取消所有订阅
        
        Returns:
            bool: 是否成功
        """
        try:
            # 清空回调函数
            self.ws_callbacks.clear()
            
            # 关闭所有WebSocket连接
            for channel, ws in self.ws_connections.items():
                try:
                    await ws.close()
                    self.logger.info(f"已关闭WebSocket连接: {channel}")
                except Exception as e:
                    self.logger.error(f"关闭WebSocket连接失败: {channel}, 错误: {e}")
            
            # 清空连接池
            self.ws_connections.clear()
            
            # 取消所有WebSocket任务
            for channel, task in self.ws_tasks.items():
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    self.logger.info(f"已取消WebSocket任务: {channel}")
            
            # 清空任务池
            self.ws_tasks.clear()
            
            return True
            
        except Exception as e:
            self.logger.error(f"取消所有订阅时发生错误: {e}")
            return False
    
    def _convert_order_type(self, order_type: OrderType) -> str:
        """
        转换订单类型
        
        Args:
            order_type: 订单类型
            
        Returns:
            str: OKX订单类型
        """
        if order_type == OrderType.MARKET:
            return 'market'
        elif order_type == OrderType.LIMIT:
            return 'limit'
        elif order_type == OrderType.POST_ONLY:
            return 'post_only'
        elif order_type == OrderType.FOK:
            return 'fok'
        elif order_type == OrderType.IOC:
            return 'ioc'
        else:
            return 'limit'  # 默认为限价单
    
    def _parse_order_type(self, order_type: str) -> OrderType:
        """
        解析订单类型
        
        Args:
            order_type: OKX订单类型
            
        Returns:
            OrderType: 订单类型
        """
        if order_type == 'market':
            return OrderType.MARKET
        elif order_type == 'limit':
            return OrderType.LIMIT
        elif order_type == 'post_only':
            return OrderType.POST_ONLY
        elif order_type == 'fok':
            return OrderType.FOK
        elif order_type == 'ioc':
            return OrderType.IOC
        else:
            return OrderType.LIMIT  # 默认为限价单
    
    def _convert_order_side(self, side: OrderSide, position_side: Optional[PositionSide] = None) -> Tuple[str, Optional[str]]:
        """
        转换订单方向
        
        Args:
            side: 订单方向
            position_side: 持仓方向
            
        Returns:
            Tuple[str, Optional[str]]: (OKX订单方向, OKX持仓方向)
        """
        # 转换订单方向
        okx_side = 'buy' if side == OrderSide.BUY else 'sell'
        
        # 转换持仓方向
        okx_pos_side = None
        if position_side is not None:
            okx_pos_side = 'long' if position_side == PositionSide.LONG else 'short'
        
        return okx_side, okx_pos_side
    
    def _parse_order_side(self, side: str, pos_side: str) -> OrderSide:
        """
        解析订单方向
        
        Args:
            side: OKX订单方向
            pos_side: OKX持仓方向
            
        Returns:
            OrderSide: 订单方向
        """
        if side == 'buy':
            return OrderSide.BUY
        else:
            return OrderSide.SELL
    
    def _convert_order_status(self, status: str) -> OrderStatus:
        """
        转换订单状态
        
        Args:
            status: OKX订单状态
            
        Returns:
            OrderStatus: 订单状态
        """
        if status == 'live':
            return OrderStatus.SUBMITTED
        elif status == 'partially_filled':
            return OrderStatus.PARTIAL
        elif status == 'filled':
            return OrderStatus.FILLED
        elif status == 'canceled':
            return OrderStatus.CANCELED
        elif status == 'canceling':
            return OrderStatus.PENDING
        else:
            return OrderStatus.PENDING
    
    def _convert_time_in_force(self, time_in_force: TimeInForce) -> str:
        """
        转换订单有效期
        
        Args:
            time_in_force: 订单有效期
            
        Returns:
            str: OKX订单有效期
        """
        if time_in_force == TimeInForce.GTC:
            return 'normal'
        elif time_in_force == TimeInForce.IOC:
            return 'ioc'
        elif time_in_force == TimeInForce.FOK:
            return 'fok'
        elif time_in_force == TimeInForce.GTX:
            return 'post_only'
        else:
            return 'normal'  # 默认为GTC
    
    def _convert_interval(self, interval: Interval) -> str:
        """
        转换时间间隔
        
        Args:
            interval: 时间间隔
            
        Returns:
            str: OKX时间间隔
        """
        interval_map = {
            Interval.MIN1: '1m',
            Interval.MIN3: '3m',
            Interval.MIN5: '5m',
            Interval.MIN15: '15m',
            Interval.MIN30: '30m',
            Interval.HOUR1: '1H',
            Interval.HOUR2: '2H',
            Interval.HOUR4: '4H',
            Interval.HOUR6: '6H',
            Interval.HOUR12: '12H',
            Interval.DAY1: '1D',
            Interval.WEEK1: '1W',
            Interval.MONTH1: '1M',
        }
        return interval_map.get(interval, '1m')
    
    def _interval_to_seconds(self, interval: Interval) -> int:
        """
        将时间间隔转换为秒数
        
        Args:
            interval: 时间间隔
            
        Returns:
            int: 秒数
        """
        interval_seconds = {
            Interval.MIN1: 60,
            Interval.MIN3: 180,
            Interval.MIN5: 300,
            Interval.MIN15: 900,
            Interval.MIN30: 1800,
            Interval.HOUR1: 3600,
            Interval.HOUR2: 7200,
            Interval.HOUR4: 14400,
            Interval.HOUR6: 21600,
            Interval.HOUR12: 43200,
            Interval.DAY1: 86400,
            Interval.WEEK1: 604800,
            Interval.MONTH1: 2592000,
        }
        return interval_seconds.get(interval, 60)
