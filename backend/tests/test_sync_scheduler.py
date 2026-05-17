"""SyncScheduler 测试 — paper 账户跳过 + 失败计数阈值告警。

回归保护：
- paper account 被错误地用真实 adapter 同步过（commit 8260988→d6b85a4 引入又修），
  这套测试盯防该过滤条件不再被移除。
- _record_sync_failure 的"连续 3 次告警"/"API 凭证立即告警"/"成功清零"三个分支。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.security import hash_password
from app.models.exchange import ExchangeAccount
from app.models.user import User
from app.services.sync_scheduler import SyncScheduler


async def _make_user(session) -> User:
    user = User(
        email="syncsched@example.com",
        name="syncsched",
        hashed_password=hash_password("password123"),
        status="active",
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def _make_account(
    session,
    user_id: int,
    *,
    name: str,
    exchange: str = "okx",
    is_paper: bool = False,
    is_active: bool = True,
) -> ExchangeAccount:
    account = ExchangeAccount(
        user_id=user_id,
        exchange=exchange,
        account_name=name,
        is_active=is_active,
        status="active",
        is_paper=is_paper,
    )
    account.set_api_key("FAKE_K_FOR_TEST_AAAAA")
    account.set_secret_key("FAKE_S_FOR_TEST_BBBBB")
    session.add(account)
    await session.flush()
    await session.refresh(account)
    return account


# ==================== paper 账户跳过 ====================


@pytest.mark.asyncio
async def test_sync_all_skips_paper_accounts(db_session, monkeypatch):
    """is_paper=True 账户不应被定时同步调用，余额由 PaperTradingService 本地维护。

    回归点：commit 8260988 加 audit 写入时漏过滤 is_paper，导致每 5 分钟一条假告警。
    """
    user = await _make_user(db_session)
    await _make_account(db_session, user.id, name="本地模拟", exchange="binance", is_paper=True)
    real = await _make_account(db_session, user.id, name="OKX 模拟", exchange="okx", is_paper=False)
    await db_session.commit()

    # 构造 session_maker 返回当前 db_session
    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=db_session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)
    session_maker = MagicMock(return_value=fake_session_cm)

    scheduler = SyncScheduler(session_maker)
    synced_account_ids: list[int] = []

    async def fake_sync_account(_session, account):
        synced_account_ids.append(account.id)

    scheduler._sync_account = fake_sync_account
    await scheduler._sync_all()

    # paper 账户不应出现在被同步列表里
    assert synced_account_ids == [real.id]


# ==================== 失败计数阈值告警 ====================


@pytest.fixture
def scheduler_with_alert_mock(monkeypatch):
    """注入一个 AsyncMock 替换 log_risk_alert，捕获每次 audit 写入。"""
    alert_mock = AsyncMock()
    monkeypatch.setattr("app.services.audit_service.log_risk_alert", alert_mock)
    scheduler = SyncScheduler(session_maker=MagicMock())
    return scheduler, alert_mock


def _make_account_obj(account_id: int = 1, name: str = "测试账户", exchange: str = "okx"):
    account = MagicMock()
    account.id = account_id
    account.account_name = name
    account.exchange = exchange
    return account


@pytest.mark.asyncio
async def test_record_sync_failure_first_two_failures_silent(scheduler_with_alert_mock):
    """普通错误前 2 次不告警，避免每 5 分钟刷屏。"""
    scheduler, alert_mock = scheduler_with_alert_mock
    account = _make_account_obj()

    await scheduler._record_sync_failure(account, RuntimeError("timeout"), source="余额同步")
    await scheduler._record_sync_failure(account, RuntimeError("timeout"), source="余额同步")

    alert_mock.assert_not_awaited()
    assert scheduler._consecutive_failures[(1, "余额同步")] == 2


@pytest.mark.asyncio
async def test_record_sync_failure_third_failure_triggers_warning(scheduler_with_alert_mock):
    """第 3 次失败触发 warning audit。"""
    scheduler, alert_mock = scheduler_with_alert_mock
    account = _make_account_obj()

    for _ in range(3):
        await scheduler._record_sync_failure(account, RuntimeError("net err"), source="余额同步")

    alert_mock.assert_awaited_once()
    kwargs = alert_mock.call_args.kwargs
    assert kwargs["severity"] == "warning"
    assert kwargs["alert_type"] == "余额同步连续失败"
    assert kwargs["metrics"]["consecutive_failures"] == 3


@pytest.mark.asyncio
async def test_record_sync_failure_api_key_invalid_immediate_critical(scheduler_with_alert_mock):
    """API 凭证错误第 1 次就立即 critical（不等阈值）。"""
    scheduler, alert_mock = scheduler_with_alert_mock
    account = _make_account_obj()

    err = Exception("BinanceAdapter: API-key format invalid.")
    await scheduler._record_sync_failure(account, err, source="余额同步")

    alert_mock.assert_awaited_once()
    kwargs = alert_mock.call_args.kwargs
    assert kwargs["severity"] == "critical"
    assert kwargs["alert_type"] == "API 凭证失效"


@pytest.mark.asyncio
async def test_clear_sync_failure_resets_counter(scheduler_with_alert_mock):
    """成功一次清该路径计数，下次失败重新从 0 累加。"""
    scheduler, alert_mock = scheduler_with_alert_mock
    account = _make_account_obj()

    await scheduler._record_sync_failure(account, RuntimeError("e1"), source="余额同步")
    await scheduler._record_sync_failure(account, RuntimeError("e2"), source="余额同步")
    scheduler._clear_sync_failure(1, "余额同步")
    assert (1, "余额同步") not in scheduler._consecutive_failures

    # 再次失败应从 1 开始计数
    await scheduler._record_sync_failure(account, RuntimeError("e3"), source="余额同步")
    assert scheduler._consecutive_failures[(1, "余额同步")] == 1
    alert_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_sync_failure_balance_and_position_independent(scheduler_with_alert_mock):
    """余额和持仓失败独立计数 — 一个一直成功不能掩盖另一个一直失败。"""
    scheduler, alert_mock = scheduler_with_alert_mock
    account = _make_account_obj()

    # 余额一直成功
    scheduler._clear_sync_failure(1, "余额同步")
    # 持仓连续失败 3 次
    for _ in range(3):
        await scheduler._record_sync_failure(account, RuntimeError("pos err"), source="持仓同步")

    alert_mock.assert_awaited_once()
    kwargs = alert_mock.call_args.kwargs
    assert kwargs["alert_type"] == "持仓同步连续失败"
    assert kwargs["metrics"]["trigger"] == "持仓同步"
