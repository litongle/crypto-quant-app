"""数据库初始化回归测试。"""

import sys
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_init_db_stamps_alembic_head_via_thread(monkeypatch, test_settings):
    """init_db 在事件循环内应通过 to_thread 调用 Alembic stamp。"""
    from app import database as database_module

    test_settings.database_url = "sqlite+aiosqlite:////tmp/crypto_quant_test.db"

    class FakeConnection:
        async def run_sync(self, fn):
            assert getattr(fn, "__name__", "") == "create_all"
            assert getattr(fn, "__self__", None) is database_module.Base.metadata

    class FakeBeginContext:
        async def __aenter__(self):
            return FakeConnection()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def begin(self):
            return FakeBeginContext()

    async def fake_get_engine():
        return FakeEngine()

    class FakeAlembicConfig:
        def __init__(self):
            self.options: dict[str, str] = {}

        def set_main_option(self, key: str, value: str):
            self.options[key] = value

    thread_calls: list[tuple] = []
    stamp_calls: list[tuple] = []

    def fake_stamp(cfg, revision):
        stamp_calls.append((cfg.options.copy(), revision))

    async def fake_to_thread(func, *args, **kwargs):
        thread_calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    monkeypatch.setattr(database_module, "get_engine", fake_get_engine)
    monkeypatch.setattr(database_module.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setitem(sys.modules, "alembic.config", SimpleNamespace(Config=FakeAlembicConfig))
    monkeypatch.setitem(
        sys.modules,
        "alembic",
        SimpleNamespace(command=SimpleNamespace(stamp=fake_stamp)),
    )

    await database_module.init_db()

    assert len(thread_calls) == 1
    assert thread_calls[0][0] is fake_stamp
    assert stamp_calls == [
        (
            {
                "script_location": "alembic",
                "sqlalchemy.url": test_settings.database_url,
            },
            "head",
        )
    ]
