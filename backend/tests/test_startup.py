"""应用启动流程回归测试。"""

import pytest


@pytest.mark.asyncio
async def test_lifespan_initializes_db_before_strategy_boot(monkeypatch):
    """启动应先建表，再 seed 模板和启动 runner。"""
    from app.main import lifespan

    calls: list[str] = []

    async def fake_init_db():
        calls.append("init_db")

    async def fake_init_strategy_templates():
        calls.append("init_strategy_templates")

    async def fake_get_session_maker():
        calls.append("get_session_maker")
        return object()

    class FakeRunner:
        async def start(self, session_maker):
            assert session_maker is not None
            calls.append("strategy_runner.start")

        async def stop(self):
            calls.append("strategy_runner.stop")

    async def fake_init_ws_proxies():
        calls.append("init_ws_proxies")

    async def fake_cleanup_ws_proxies():
        calls.append("cleanup_ws_proxies")

    async def fake_start_reconciliation(session_maker):
        assert session_maker is not None
        calls.append("start_reconciliation")

    async def fake_stop_reconciliation():
        calls.append("stop_reconciliation")

    async def fake_start_sync_scheduler(session_maker):
        assert session_maker is not None
        calls.append("start_sync_scheduler")

    async def fake_stop_sync_scheduler():
        calls.append("stop_sync_scheduler")

    async def fake_close_redis():
        calls.append("close_redis")

    async def fake_reset_database():
        calls.append("reset_database")

    class FakeNotificationService:
        async def close(self):
            calls.append("notification_service.close")

    monkeypatch.setattr("app.database.init_db", fake_init_db)
    monkeypatch.setattr("app.seed_data.init_strategy_templates", fake_init_strategy_templates)
    monkeypatch.setattr("app.database.get_session_maker", fake_get_session_maker)
    monkeypatch.setattr("app.core.strategy_runner.strategy_runner", FakeRunner())
    monkeypatch.setattr("app.api.v1.ws_market.init_ws_proxies", fake_init_ws_proxies)
    monkeypatch.setattr("app.api.v1.ws_market.cleanup_ws_proxies", fake_cleanup_ws_proxies)
    monkeypatch.setattr(
        "app.services.order_reconciliation_service.start_reconciliation",
        fake_start_reconciliation,
    )
    monkeypatch.setattr(
        "app.services.order_reconciliation_service.stop_reconciliation",
        fake_stop_reconciliation,
    )
    monkeypatch.setattr(
        "app.services.sync_scheduler.start_sync_scheduler", fake_start_sync_scheduler
    )
    monkeypatch.setattr("app.services.sync_scheduler.stop_sync_scheduler", fake_stop_sync_scheduler)
    monkeypatch.setattr("app.redis.close_redis", fake_close_redis)
    monkeypatch.setattr("app.database.reset_database", fake_reset_database)
    monkeypatch.setattr(
        "app.services.notification_service.notification_service",
        FakeNotificationService(),
    )

    async with lifespan(object()):
        pass

    assert "init_db" in calls
    assert "init_strategy_templates" in calls
    assert "strategy_runner.start" in calls
    assert calls.index("init_db") < calls.index("init_strategy_templates")
    assert calls.index("init_db") < calls.index("strategy_runner.start")
