"""
自定义异常定义
"""
from typing import Any


class AppException(Exception):
    """应用基础异常"""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


# 认证异常
class AuthenticationError(AppException):
    """认证错误"""

    def __init__(self, message: str = "认证失败"):
        super().__init__(message, code="AUTHENTICATION_ERROR")


class InvalidCredentialsError(AuthenticationError):
    """凭证无效"""

    def __init__(self):
        super().__init__("用户名或密码错误")


class TokenExpiredError(AuthenticationError):
    """Token 过期"""

    def __init__(self):
        super().__init__("Token 已过期，请重新登录")


# 资源异常
class NotFoundError(AppException):
    """资源不存在"""

    def __init__(self, resource: str, identifier: str | int):
        super().__init__(
            message=f"{resource} {identifier} 不存在",
            code="NOT_FOUND",
        )


class AlreadyExistsError(AppException):
    """资源已存在"""

    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} {identifier} 已存在",
            code="ALREADY_EXISTS",
        )


# 业务异常
class ValidationError(AppException):
    """验证错误"""

    def __init__(self, message: str, field: str | None = None):
        details = {"field": field} if field else {}
        super().__init__(message, code="VALIDATION_ERROR", details=details)


class InsufficientBalanceError(AppException):
    """余额不足"""

    def __init__(self, required: str, available: str):
        super().__init__(
            message=f"余额不足：需要 {required}，可用 {available}",
            code="INSUFFICIENT_BALANCE",
            details={"required": required, "available": available},
        )


class RiskLimitExceededError(AppException):
    """风控限制超限"""

    def __init__(self, message: str):
        super().__init__(message, code="RISK_LIMIT_EXCEEDED")


# 交易异常
class OrderError(AppException):
    """订单错误"""

    def __init__(self, message: str, exchange: str | None = None):
        details = {"exchange": exchange} if exchange else {}
        super().__init__(message, code="ORDER_ERROR", details=details)


class ExchangeAPIError(OrderError):
    """交易所 API 错误

    Attributes:
        exchange: 交易所名称
        retryable: 是否可重试（429限流、网络超时等）
        status_code: HTTP 状态码（如果有）
        detail_code: 交易所错误码（如果有）
    """

    def __init__(
        self,
        exchange: str,
        message: str,
        retryable: bool = False,
        status_code: int | None = None,
        detail_code: str | None = None,
    ):
        super().__init__(f"{exchange}: {message}", exchange=exchange)
        self.code = "EXCHANGE_API_ERROR"
        self.exchange = exchange
        self.retryable = retryable
        self.status_code = status_code
        self.detail_code = detail_code


class RateLimitError(ExchangeAPIError):
    """交易所限流错误（429）— 可重试"""

    def __init__(self, exchange: str, message: str = "请求频率超限"):
        super().__init__(
            exchange, message,
            retryable=True,
            status_code=429,
        )
        self.code = "RATE_LIMIT_ERROR"


class NetworkError(ExchangeAPIError):
    """网络连接错误（超时/DNS/连接重置）— 可重试"""

    def __init__(self, exchange: str, message: str = "网络连接异常"):
        super().__init__(
            exchange, message,
            retryable=True,
        )
        self.code = "NETWORK_ERROR"


class OrderRejectedError(ExchangeAPIError):
    """订单被交易所拒绝（余额不足/风控/参数错误）— 不可重试"""

    def __init__(
        self,
        exchange: str,
        message: str,
        detail_code: str | None = None,
    ):
        super().__init__(
            exchange, message,
            retryable=False,
            detail_code=detail_code,
        )
        self.code = "ORDER_REJECTED"
