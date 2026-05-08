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
            name = getattr(fn, "__name__", "")
            if name == "_inspect_schema_state":
                return {
                    "table_names": set(),
                    "strategy_columns": set(),
                    "has_app_tables": False,
                    "has_alembic_version": False,
                }
            if name == "create_all":
                assert getattr(fn, "__self__", None) is database_module.Base.metadata
                return None
            if name == "_repair_strategy_instances_schema":
                return False
            raise AssertionError(f"unexpected run_sync call: {name}")

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


@pytest.mark.asyncio
async def test_init_db_upgrades_existing_schema_before_repair(monkeypatch, test_settings):
    """已有业务表时，应优先执行 Alembic upgrade，而不是继续 stamp head。"""
    from app import database as database_module

    test_settings.database_url = "sqlite+aiosqlite:////tmp/crypto_quant_test.db"

    class FakeConnection:
        async def run_sync(self, fn):
            name = getattr(fn, "__name__", "")
            if name == "_inspect_schema_state":
                return {
                    "table_names": {"strategy_instances", "users", "strategy_templates"},
                    "strategy_columns": {"id", "status"},
                    "has_app_tables": True,
                    "has_alembic_version": True,
                    "current_revision": "0007",
                }
            if name == "create_all":
                raise AssertionError("create_all should not be called for managed existing DB")
            if name == "_repair_strategy_instances_schema":
                return True
            raise AssertionError(f"unexpected run_sync call: {name}")

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
    upgrade_calls: list[tuple] = []
    stamp_calls: list[tuple] = []

    def fake_upgrade(cfg, revision):
        upgrade_calls.append((cfg.options.copy(), revision))

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
        SimpleNamespace(command=SimpleNamespace(stamp=fake_stamp, upgrade=fake_upgrade)),
    )

    await database_module.init_db()

    assert len(thread_calls) == 1
    assert thread_calls[0][0] is fake_upgrade
    assert upgrade_calls == [
        (
            {
                "script_location": "alembic",
                "sqlalchemy.url": test_settings.database_url,
            },
            "head",
        )
    ]
    assert stamp_calls == []


@pytest.mark.asyncio
async def test_init_db_skips_alembic_replay_for_existing_schema_without_version(
    monkeypatch, test_settings
):
    """已有业务表但没有 alembic_version 时，不应误跑历史迁移。"""
    from app import database as database_module

    test_settings.database_url = "sqlite+aiosqlite:////tmp/crypto_quant_test.db"

    class FakeConnection:
        async def run_sync(self, fn):
            name = getattr(fn, "__name__", "")
            if name == "_inspect_schema_state":
                return {
                    "table_names": {"strategy_instances", "users", "strategy_templates"},
                    "strategy_columns": {"id", "status"},
                    "has_app_tables": True,
                    "has_alembic_version": False,
                    "current_revision": None,
                }
            if name == "create_all":
                return None
            if name == "_repair_strategy_instances_schema":
                return True
            raise AssertionError(f"unexpected run_sync call: {name}")

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

    def fake_upgrade(*args, **kwargs):
        raise AssertionError("upgrade should not be called")

    def fake_stamp(*args, **kwargs):
        raise AssertionError("stamp should not be called")

    async def fake_to_thread(func, *args, **kwargs):
        thread_calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    monkeypatch.setattr(database_module, "get_engine", fake_get_engine)
    monkeypatch.setattr(database_module.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setitem(sys.modules, "alembic.config", SimpleNamespace(Config=FakeAlembicConfig))
    monkeypatch.setitem(
        sys.modules,
        "alembic",
        SimpleNamespace(command=SimpleNamespace(stamp=fake_stamp, upgrade=fake_upgrade)),
    )

    await database_module.init_db()

    assert thread_calls == []


@pytest.mark.asyncio
async def test_init_db_raises_when_upgrade_fails_for_managed_existing_db(
    monkeypatch, test_settings
):
    """已有 alembic_version 的库升级失败时，应中止启动而不是静默放过。"""
    from app import database as database_module

    test_settings.database_url = "sqlite+aiosqlite:////tmp/crypto_quant_test.db"

    class FakeConnection:
        async def run_sync(self, fn):
            name = getattr(fn, "__name__", "")
            if name == "_inspect_schema_state":
                return {
                    "table_names": {
                        "strategy_instances",
                        "users",
                        "strategy_templates",
                        "alembic_version",
                    },
                    "strategy_columns": {"id", "status"},
                    "has_app_tables": True,
                    "has_alembic_version": True,
                    "current_revision": "0007",
                }
            if name == "create_all":
                raise AssertionError("create_all should not be called for managed existing DB")
            raise AssertionError(f"unexpected run_sync call: {name}")

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

    def fake_upgrade(cfg, revision):
        raise RuntimeError("boom")

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(database_module, "get_engine", fake_get_engine)
    monkeypatch.setattr(database_module.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setitem(sys.modules, "alembic.config", SimpleNamespace(Config=FakeAlembicConfig))
    monkeypatch.setitem(
        sys.modules,
        "alembic",
        SimpleNamespace(command=SimpleNamespace(upgrade=fake_upgrade)),
    )

    with pytest.raises(RuntimeError, match="boom"):
        await database_module.init_db()
