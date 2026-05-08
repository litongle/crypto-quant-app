"""
通用响应模式
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """统一 API 响应格式"""

    model_config = ConfigDict(
        json_schema_extra={"example": {"code": 0, "message": "success", "data": {"key": "value"}}}
    )

    code: int = 0
    message: str = "success"
    data: T | None = None


class PageResponse(BaseModel, Generic[T]):
    """分页响应"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": 0,
                "message": "success",
                "data": [{"key": "value"}],
                "total": 100,
                "page": 1,
                "pageSize": 20,
            }
        }
    )

    code: int = 0
    message: str = "success"
    data: list[T] | None = None
    total: int = 0
    page: int = 1
    page_size: int = Field(default=20, alias="pageSize")
