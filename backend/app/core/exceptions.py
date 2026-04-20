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
    """交易所 API 错误"""

    def __init__(self, exchange: str, message: str):
        super().__init__(f"{exchange}: {message}", exchange=exchange)
        self.code = "EXCHANGE_API_ERROR"
