"""
error_handling 单元测试

覆盖:
- trace_id 生成 / 设置 / 清空 / contextvar 隔离
- retry_on_retryable: 同步函数 / 异步函数
- 重试判定: ExchangeAPIError(retryable=True) 重试; OrderRejected 不重试;
  普通 Exception 默认重试;耗尽后抛原异常
"""
from __future__ import annotations

import asyncio

import pytest

from app.core.error_handling import (
    clear_trace_id,
    get_trace_id,
    retry_on_retryable,
    set_trace_id,
)
from app.core.exceptions import (
    AppException,
    NetworkError,
    OrderRejectedError,
    RateLimitError,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── trace_id ──────────────────────────────────────────────

class TestTraceId:
    def setup_method(self):
        clear_trace_id()

    def test_first_access_generates_uuid(self):
        tid = get_trace_id()
        assert isinstance(tid, str)
        assert len(tid) == 32  # UUID4 hex

    def test_second_access_returns_same(self):
        tid1 = get_trace_id()
        tid2 = get_trace_id()
        assert tid1 == tid2

    def test_set_overrides(self):
        token = set_trace_id("custom-trace-abc")
        try:
            assert get_trace_id() == "custom-trace-abc"
        finally:
            # 还原(其他测试不受影响)
            import contextvars  # noqa: F401
            from app.core.error_handling import _trace_id_var
            _trace_id_var.reset(token)

    def test_clear_resets(self):
        set_trace_id("temp")
        assert get_trace_id() == "temp"
        clear_trace_id()
        # 清空后再访问应生成新的
        new_tid = get_trace_id()
        assert new_tid != "temp"

    def test_contextvar_isolated_across_async_tasks(self):
        """两个并发协程应有独立的 trace_id(contextvar 自动复制)"""
        results: dict[str, str] = {}

        async def task(name: str, tid: str):
            set_trace_id(tid)
            await asyncio.sleep(0.01)
            results[name] = get_trace_id()

        async def main():
            await asyncio.gather(
                task("a", "trace-a"),
                task("b", "trace-b"),
            )

        run(main())
        assert results["a"] == "trace-a"
        assert results["b"] == "trace-b"


# ── retry_on_retryable: 同步 ───────────────────────────────

class TestRetrySync:
    def test_succeeds_first_try_no_retry(self):
        calls = {"n": 0}

        @retry_on_retryable(max_attempts=3, min_wait_seconds=0.01)
        def fn():
            calls["n"] += 1
            return "ok"

        assert fn() == "ok"
        assert calls["n"] == 1

    def test_retries_retryable_exchange_error(self):
        calls = {"n": 0}

        @retry_on_retryable(max_attempts=3, min_wait_seconds=0.01)
        def fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RateLimitError(exchange="okx")
            return "ok"

        assert fn() == "ok"
        assert calls["n"] == 3

    def test_does_not_retry_order_rejected(self):
        calls = {"n": 0}

        @retry_on_retryable(max_attempts=3, min_wait_seconds=0.01)
        def fn():
            calls["n"] += 1
            raise OrderRejectedError(exchange="okx", message="余额不足")

        with pytest.raises(OrderRejectedError):
            fn()
        assert calls["n"] == 1  # 不可重试,只调一次

    def test_retries_plain_exception(self):
        """非 AppException(网络/IO 类原始异常)默认按瞬时故障重试"""
        calls = {"n": 0}

        @retry_on_retryable(max_attempts=3, min_wait_seconds=0.01)
        def fn():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ConnectionError("boom")
            return "ok"

        assert fn() == "ok"
        assert calls["n"] == 2

    def test_does_not_retry_business_appexception(self):
        """普通 AppException(非 ExchangeAPIError)不该重试"""
        calls = {"n": 0}

        @retry_on_retryable(max_attempts=3, min_wait_seconds=0.01)
        def fn():
            calls["n"] += 1
            raise AppException(message="业务错误", code="VALIDATION_ERROR")

        with pytest.raises(AppException):
            fn()
        assert calls["n"] == 1

    def test_exhausted_raises_last_original_exception(self):
        """重试耗尽后抛出最后一次的原始异常,不是 RetryError"""
        @retry_on_retryable(max_attempts=2, min_wait_seconds=0.01)
        def fn():
            raise NetworkError(exchange="binance", message="超时")

        with pytest.raises(NetworkError):
            fn()


# ── retry_on_retryable: 异步 ───────────────────────────────

class TestRetryAsync:
    def test_async_succeeds_first_try(self):
        calls = {"n": 0}

        @retry_on_retryable(max_attempts=3, min_wait_seconds=0.01)
        async def fn():
            calls["n"] += 1
            return "ok"

        assert run(fn()) == "ok"
        assert calls["n"] == 1

    def test_async_retries_until_success(self):
        calls = {"n": 0}

        @retry_on_retryable(max_attempts=4, min_wait_seconds=0.01)
        async def fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise NetworkError(exchange="okx")
            return "ok"

        assert run(fn()) == "ok"
        assert calls["n"] == 3

    def test_async_exhausted_raises_original(self):
        @retry_on_retryable(max_attempts=2, min_wait_seconds=0.01)
        async def fn():
            raise RateLimitError(exchange="huobi")

        with pytest.raises(RateLimitError):
            run(fn())

    def test_async_does_not_retry_order_rejected(self):
        calls = {"n": 0}

        @retry_on_retryable(max_attempts=3, min_wait_seconds=0.01)
        async def fn():
            calls["n"] += 1
            raise OrderRejectedError(exchange="okx", message="参数错误")

        with pytest.raises(OrderRejectedError):
            run(fn())
        assert calls["n"] == 1


# ── 自定义重试判定 ────────────────────────────────────────

class TestCustomRetryPredicate:
    def test_custom_is_retryable_only_on_value_error(self):
        calls = {"n": 0}

        @retry_on_retryable(
            max_attempts=3,
            min_wait_seconds=0.01,
            is_retryable=lambda e: isinstance(e, ValueError),
        )
        def fn():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ValueError("retry me")
            raise TypeError("don't retry me")

        with pytest.raises(TypeError):
            fn()
        # 第 1 次 ValueError(重试) → 第 2 次 TypeError(不重试,直接抛)
        assert calls["n"] == 2
