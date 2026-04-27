"""
错误处理基础设施

从 gc/app/utils/error_handling.py 精简吸收。
保留对当前架构有价值的部分,丢弃过度设计:

吸收:
  - trace_id 线程本地存储 — 跨日志/异常关联同一请求
  - retry_with_backoff 装饰器 — 基于 tenacity,默认只重试可重试异常

不吸收:
  - 自定义 AppError + ErrorCode 枚举 → 主仓 app.core.exceptions 已更完善
  - pybreaker 断路器 → 重依赖,先用 ExchangeAPIError.retryable 覆盖
  - structlog 重新配置 → 留给 observability 专题
  - 微信/Slack/钉钉 webhook 告警 → 上生产前过早

使用示例:
    from app.core.error_handling import retry_on_retryable, set_trace_id, get_trace_id

    @retry_on_retryable(max_attempts=3)
    async def call_exchange():
        ...
"""
from __future__ import annotations

import contextvars
import functools
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar, cast

from tenacity import (
    AsyncRetrying,
    RetryError,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.exceptions import AppException, ExchangeAPIError

logger = logging.getLogger(__name__)


# ── trace_id ────────────────────────────────────────────────
#
# 用 contextvars 而不是 threading.local: 在 asyncio 协程间正确传递,
# threading.local 在 async 上下文里会串味。

_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)


def get_trace_id() -> str:
    """取当前上下文的 trace_id;首次访问时自动生成 UUID4。"""
    tid = _trace_id_var.get()
    if tid is None:
        tid = uuid.uuid4().hex
        _trace_id_var.set(tid)
    return tid


def set_trace_id(trace_id: str) -> contextvars.Token[str | None]:
    """显式设置 trace_id,返回 Token 以供 reset 还原。

    通常由 HTTP 中间件在请求入口处调用,把 X-Request-ID 头注入上下文。
    """
    return _trace_id_var.set(trace_id)


def clear_trace_id() -> None:
    """清空当前上下文的 trace_id。"""
    _trace_id_var.set(None)


# ── 重试装饰器 ──────────────────────────────────────────────

P = ParamSpec("P")
T = TypeVar("T")


def _is_retryable(exc: BaseException) -> bool:
    """默认重试判定: 仅重试明确标记 retryable 的异常。

    - ExchangeAPIError(retryable=True) → 是
    - 其他 AppException 子类 → 否(交易拒单/余额不足/参数错误等不该重试)
    - 非 AppException(网络/IO 等) → 是(假定为瞬时故障)
    """
    if isinstance(exc, ExchangeAPIError):
        return bool(getattr(exc, "retryable", False))
    if isinstance(exc, AppException):
        return False
    return True


def retry_on_retryable(
    *,
    max_attempts: int = 3,
    min_wait_seconds: float = 0.5,
    max_wait_seconds: float = 10.0,
    is_retryable: Callable[[BaseException], bool] = _is_retryable,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """指数退避重试装饰器。同时支持同步/异步函数。

    Args:
        max_attempts: 最多尝试次数(含首次)
        min_wait_seconds: 首次退避最小等待
        max_wait_seconds: 退避上限
        is_retryable: 判定函数,决定哪些异常触发重试。默认见 _is_retryable。

    抛出:
        最后一次的原始异常(不包成 RetryError)。
    """
    wait = wait_exponential(
        multiplier=min_wait_seconds, min=min_wait_seconds, max=max_wait_seconds
    )
    stop = stop_after_attempt(max_attempts)
    retry_cond = retry_if_exception(is_retryable)

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        import asyncio

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                try:
                    async for attempt in AsyncRetrying(
                        stop=stop,
                        wait=wait,
                        retry=retry_cond,
                        reraise=True,
                        before_sleep=_log_retry,
                    ):
                        with attempt:
                            return await cast(
                                Callable[..., Awaitable[T]], func
                            )(*args, **kwargs)
                except RetryError as e:  # 兜底(reraise=True 通常不会到这)
                    raise e.last_attempt.exception() or e
                raise RuntimeError("unreachable")  # type: ignore[unreachable]

            return cast(Callable[P, T], async_wrapper)

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                for attempt in Retrying(
                    stop=stop,
                    wait=wait,
                    retry=retry_cond,
                    reraise=True,
                    before_sleep=_log_retry,
                ):
                    with attempt:
                        return func(*args, **kwargs)
            except RetryError as e:
                raise e.last_attempt.exception() or e
            raise RuntimeError("unreachable")  # type: ignore[unreachable]

        return sync_wrapper

    return decorator


def _log_retry(retry_state: Any) -> None:
    """重试前的日志钩子"""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "[retry] %s 第 %d 次失败,准备重试: %s (trace=%s)",
        retry_state.fn.__name__ if retry_state.fn else "<unknown>",
        retry_state.attempt_number,
        exc,
        get_trace_id(),
    )
