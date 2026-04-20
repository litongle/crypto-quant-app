"""
通用响应模式
"""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """统一 API 响应格式"""
    code: int = 0
    message: str = "success"
    data: T | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "code": 0,
                "message": "success",
                "data": {"key": "value"}
            }
        }


class PageResponse(BaseModel, Generic[T]):
    """分页响应"""
    code: int = 0
    message: str = "success"
    data: list[T] | None = None
    total: int = 0
    page: int = 1
    pageSize: int = 20

    class Config:
        json_schema_extra = {
            "example": {
                "code": 0,
                "message": "success",
                "data": [{"key": "value"}],
                "total": 100,
                "page": 1,
                "pageSize": 20
            }
        }
