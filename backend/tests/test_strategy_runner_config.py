"""策略 runner 风控阈值切换数据源的回归测试。"""

import pytest

from app.core.strategy_runner import _get_auto_pause_config
from app.services.runtime_config_service import RuntimeConfigService


@pytest.mark.asyncio
async def test_get_auto_pause_config_reads_runtime_values(db_session):
    svc = RuntimeConfigService(db_session)
    await svc.set("AUTO_PAUSE_WATCHDOG_INTERVAL_SECONDS", "42", encrypt=False)
    await svc.set("AUTO_PAUSE_CONSECUTIVE_ERRORS", "7", encrypt=False)

    cfg = await _get_auto_pause_config(db_session)
    assert cfg["watchdog_interval_seconds"] == 42
    assert cfg["consecutive_errors"] == 7


@pytest.mark.asyncio
async def test_get_auto_pause_config_falls_back_to_defaults(db_session):
    cfg = await _get_auto_pause_config(db_session)
    assert cfg["watchdog_interval_seconds"] == 30
    assert cfg["consecutive_errors"] == 5
    assert cfg["consecutive_order_failures"] == 3
    assert cfg["heartbeat_multiplier"] == 5
    assert cfg["heartbeat_min_seconds"] == 300
