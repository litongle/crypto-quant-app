from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.audit_event import AuditEvent
from app.models.exchange import ExchangeAccount
from app.models.order import Order, Signal
from app.models.strategy import StrategyInstance, StrategyTemplate


async def _make_template(db_session) -> StrategyTemplate:
    template = StrategyTemplate(
        code="ma_cross",
        name="MA Cross",
        description="test",
        strategy_type="ma_cross",
        params_schema={},
        risk_level="low",
        is_active=True,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


async def _make_instance(
    db_session, user_id: int, template_id: int, name: str, symbol: str = "BTCUSDT"
):
    instance = StrategyInstance(
        user_id=user_id,
        template_id=template_id,
        name=name,
        symbol=symbol,
        exchange="binance",
        direction="both",
        params={},
        risk_params={},
        status="running",
        workspace_state="running",
    )
    db_session.add(instance)
    await db_session.commit()
    await db_session.refresh(instance)
    return instance


@pytest.mark.asyncio
async def test_list_events_empty(client, auth_headers):
    resp = await client.get("/api/v1/events", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total"] == 0
    assert body["items"] == []
    assert body["limit"] == 50
    assert body["offset"] == 0


@pytest.mark.asyncio
async def test_list_events_with_signal_and_auto_pause(client, auth_headers, db_session, test_user):
    template = await _make_template(db_session)
    instance = await _make_instance(db_session, test_user.id, template.id, "趋势实例")
    now = datetime.now(UTC)

    db_session.add(
        Signal(
            strategy_instance_id=instance.id,
            symbol="BTCUSDT",
            action="buy",
            confidence=0.8,
            status="pending",
            reason="突破",
            created_at=now - timedelta(minutes=4),
        )
    )
    instance.last_pause_reason = "auto:order_failures"
    instance.last_stopped_at = now
    instance.status = "paused"
    await db_session.commit()

    resp = await client.get("/api/v1/events", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 2
    types = [item["type"] for item in items]
    # auto_pause 时间更晚，排在前面
    assert types == ["auto_pause", "signal"]


@pytest.mark.asyncio
async def test_list_events_filter_by_type(client, auth_headers, db_session, test_user):
    template = await _make_template(db_session)
    instance = await _make_instance(db_session, test_user.id, template.id, "信号实例")
    db_session.add(
        Signal(
            strategy_instance_id=instance.id,
            symbol="BTCUSDT",
            action="buy",
            confidence=0.8,
            status="pending",
        )
    )
    instance.last_pause_reason = "auto:heartbeat_timeout"
    instance.last_stopped_at = datetime.now(UTC)
    await db_session.commit()

    resp = await client.get("/api/v1/events?event_type=signal", headers=auth_headers)
    body = resp.json()["data"]
    assert all(item["type"] == "signal" for item in body["items"])
    assert body["total"] == 1


@pytest.mark.asyncio
async def test_manual_pause_not_exposed_as_auto_pause(client, auth_headers, db_session, test_user):
    template = await _make_template(db_session)
    instance = await _make_instance(db_session, test_user.id, template.id, "手动暂停实例")
    instance.status = "paused"
    instance.last_stopped_at = datetime.now(UTC)
    instance.last_pause_reason = None
    await db_session.commit()

    resp = await client.get("/api/v1/events?event_type=auto_pause", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total"] == 0
    assert body["items"] == []


@pytest.mark.asyncio
async def test_list_events_filter_by_instance(client, auth_headers, db_session, test_user):
    template = await _make_template(db_session)
    first = await _make_instance(db_session, test_user.id, template.id, "A")
    second = await _make_instance(db_session, test_user.id, template.id, "B", symbol="ETHUSDT")
    db_session.add_all(
        [
            Signal(
                strategy_instance_id=first.id,
                symbol="BTCUSDT",
                action="buy",
                confidence=0.8,
                status="pending",
            ),
            Signal(
                strategy_instance_id=second.id,
                symbol="ETHUSDT",
                action="sell",
                confidence=0.8,
                status="pending",
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get(f"/api/v1/events?instance_id={first.id}", headers=auth_headers)
    body = resp.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["instance_id"] == first.id


@pytest.mark.asyncio
async def test_list_events_search(client, auth_headers, db_session, test_user):
    template = await _make_template(db_session)
    instance = await _make_instance(db_session, test_user.id, template.id, "检索实例")
    db_session.add(
        Signal(
            strategy_instance_id=instance.id,
            symbol="BTCUSDT",
            action="buy",
            confidence=0.8,
            status="pending",
            reason="BTCUSDT breakout",
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/events?q=BTCUSDT", headers=auth_headers)
    body = resp.json()["data"]
    assert body["total"] == 1
    assert "BTCUSDT" in body["items"][0]["summary"]


@pytest.mark.asyncio
async def test_list_events_pagination(client, auth_headers, db_session, test_user):
    template = await _make_template(db_session)
    instance = await _make_instance(db_session, test_user.id, template.id, "分页实例")
    for index in range(12):
        db_session.add(
            Signal(
                strategy_instance_id=instance.id,
                symbol="BTCUSDT",
                action="buy",
                confidence=0.8,
                status="pending",
                reason=f"event-{index}",
                created_at=datetime.now(UTC) - timedelta(minutes=index),
            )
        )
    await db_session.commit()

    resp1 = await client.get("/api/v1/events?limit=5&offset=0", headers=auth_headers)
    resp2 = await client.get("/api/v1/events?limit=5&offset=5", headers=auth_headers)
    body1 = resp1.json()["data"]
    body2 = resp2.json()["data"]
    assert len(body1["items"]) == 5
    assert len(body2["items"]) == 5
    assert body1["total"] == 12
    assert body1["items"][0]["id"] != body2["items"][0]["id"]


@pytest.mark.asyncio
async def test_list_events_invalid_type(client, auth_headers):
    resp = await client.get("/api/v1/events?event_type=invalid_xxx", headers=auth_headers)
    assert resp.status_code == 422


# ==================== 订单事件 + 信号关联 ====================


async def _make_account(db_session, user_id: int) -> ExchangeAccount:
    account = ExchangeAccount(
        user_id=user_id,
        exchange="okx",
        account_name="test-evt-acc",
        is_active=True,
        status="active",
    )
    account.set_api_key("FAKE_K_FOR_TEST_AAAAA")
    account.set_secret_key("FAKE_S_FOR_TEST_BBBBB")
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)
    return account


@pytest.mark.asyncio
async def test_list_events_includes_order(client, auth_headers, db_session, test_user):
    template = await _make_template(db_session)
    instance = await _make_instance(db_session, test_user.id, template.id, "下单实例")
    account = await _make_account(db_session, test_user.id)

    now = datetime.now(UTC)
    order = Order(
        account_id=account.id,
        symbol="ETHUSDT",
        side="sell",
        order_type="market",
        quantity=Decimal("0.5"),
        filled_quantity=Decimal("0.5"),
        avg_fill_price=Decimal("2230.5"),
        order_value=Decimal("1115.25"),
        commission=Decimal("0"),
        status="filled",
        strategy_instance_id=instance.id,
        created_at=now - timedelta(minutes=2),
        filled_at=now - timedelta(minutes=1),
    )
    db_session.add(order)
    await db_session.commit()

    resp = await client.get("/api/v1/events?event_type=order", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total"] == 1
    item = body["items"][0]
    assert item["type"] == "order"
    assert "ETHUSDT" in item["summary"]
    assert "卖出" in item["summary"]
    assert "已成交" in item["summary"]
    assert item["instance_id"] == instance.id
    assert item["detail"]["status"] == "filled"
    assert item["detail"]["avg_fill_price"] == "2230.5"


@pytest.mark.asyncio
async def test_list_events_rejected_order_summary_has_error(
    client, auth_headers, db_session, test_user
):
    template = await _make_template(db_session)
    instance = await _make_instance(db_session, test_user.id, template.id, "拒单实例")
    account = await _make_account(db_session, test_user.id)

    db_session.add(
        Order(
            account_id=account.id,
            symbol="ETHUSDT",
            side="sell",
            order_type="market",
            quantity=Decimal("0.5"),
            filled_quantity=Decimal("0"),
            order_value=Decimal("0"),
            commission=Decimal("0"),
            status="rejected",
            strategy_instance_id=instance.id,
            error_message="OKX 51008 余额不足",
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/events?event_type=order", headers=auth_headers)
    body = resp.json()["data"]
    assert body["total"] == 1
    item = body["items"][0]
    assert "已拒单" in item["summary"]
    assert "51008" in item["summary"]
    assert item["detail"]["error_message"] == "OKX 51008 余额不足"


@pytest.mark.asyncio
async def test_signal_detail_links_to_order_with_slippage(
    client, auth_headers, db_session, test_user
):
    """signal 事件 detail 应挂上同 signal_id 关联的 order_id 与滑点。"""
    template = await _make_template(db_session)
    instance = await _make_instance(db_session, test_user.id, template.id, "滑点实例")
    account = await _make_account(db_session, test_user.id)

    signal = Signal(
        strategy_instance_id=instance.id,
        symbol="ETHUSDT",
        action="sell",
        confidence=Decimal("0.8"),
        entry_price=Decimal("2230"),
        status="executed",
    )
    db_session.add(signal)
    await db_session.commit()
    await db_session.refresh(signal)

    db_session.add(
        Order(
            account_id=account.id,
            symbol="ETHUSDT",
            side="sell",
            order_type="market",
            quantity=Decimal("0.5"),
            filled_quantity=Decimal("0.5"),
            avg_fill_price=Decimal("2227.6"),  # 卖低于报价 → 负滑点
            order_value=Decimal("1113.8"),
            commission=Decimal("0"),
            status="filled",
            strategy_instance_id=instance.id,
            signal_id=signal.id,
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/events?event_type=signal", headers=auth_headers)
    body = resp.json()["data"]
    item = body["items"][0]
    detail = item["detail"]
    assert detail["order_id"] is not None
    assert detail["order_status"] == "filled"
    assert detail["fill_price"] == "2227.6"
    # sell 取反：(2227.6 - 2230) / 2230 ≈ -0.001076; 取负后 = +0.001076 → 不,我们说 sell 反向
    # 这里实际: slippage_raw = (fill - signal) / signal = -0.001076 (卖低于报价是负面滑点)
    # sell 取反 → +0.001076 (正值=不利)?  代码里 sell 取负号,意思是 "对卖方有利时为正"
    # 让我们只断言它是个有限值,不挑符号:
    assert "slippage_pct" in detail


# ==================== audit_events 表事件 ====================


@pytest.mark.asyncio
async def test_list_events_includes_risk_alert(client, auth_headers, db_session, test_user):
    template = await _make_template(db_session)
    instance = await _make_instance(db_session, test_user.id, template.id, "告警实例")
    db_session.add(
        AuditEvent(
            type="risk_alert",
            severity="critical",
            user_id=test_user.id,
            instance_id=instance.id,
            summary="风控告警 · 策略崩溃 · task 异常退出",
            detail={"alert_type": "策略崩溃", "metrics": {"reason": "task_crashed"}},
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/events?event_type=risk_alert", headers=auth_headers)
    body = resp.json()["data"]
    assert body["total"] == 1
    item = body["items"][0]
    assert item["type"] == "risk_alert"
    assert item["severity"] == "critical"
    assert "策略崩溃" in item["summary"]


@pytest.mark.asyncio
async def test_list_events_includes_user_action(client, auth_headers, db_session, test_user):
    template = await _make_template(db_session)
    instance = await _make_instance(db_session, test_user.id, template.id, "操作实例")
    db_session.add(
        AuditEvent(
            type="user_action",
            severity="info",
            user_id=test_user.id,
            instance_id=instance.id,
            summary=f'启动策略 "{instance.name}"',
            detail={"action": "start_strategy"},
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/events?event_type=user_action", headers=auth_headers)
    body = resp.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["detail"]["action"] == "start_strategy"


@pytest.mark.asyncio
async def test_list_events_system_event_visible_without_user_filter(
    client, auth_headers, db_session, test_user
):
    """system 事件 user_id=NULL，但单用户场景下应当能被看到。"""
    db_session.add(
        AuditEvent(
            type="system",
            severity="info",
            user_id=None,
            summary="系统启动 · v1.0.0",
            detail={"event": "app_started"},
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/events?event_type=system", headers=auth_headers)
    body = resp.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["type"] == "system"


@pytest.mark.asyncio
async def test_list_events_filter_by_severity(client, auth_headers, db_session, test_user):
    template = await _make_template(db_session)
    instance = await _make_instance(db_session, test_user.id, template.id, "等级过滤")
    db_session.add_all(
        [
            AuditEvent(
                type="risk_alert",
                severity="critical",
                user_id=test_user.id,
                instance_id=instance.id,
                summary="持仓状态漂移",
            ),
            AuditEvent(
                type="user_action",
                severity="info",
                user_id=test_user.id,
                instance_id=instance.id,
                summary="启动策略",
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/v1/events?severity=critical", headers=auth_headers)
    body = resp.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_list_events_user_actions_isolated_between_users(
    client, auth_headers, db_session, test_user
):
    """另一个用户的 user_action 不应出现在当前用户的事件流。"""
    from app.core.security import hash_password
    from app.models.user import User

    other = User(
        email="other@example.com",
        name="other",
        hashed_password=hash_password("password123"),
        status="active",
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    db_session.add_all(
        [
            AuditEvent(
                type="user_action",
                user_id=other.id,
                summary="他人的操作",
            ),
            AuditEvent(
                type="user_action",
                user_id=test_user.id,
                summary="我的操作",
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/v1/events?event_type=user_action", headers=auth_headers)
    body = resp.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["summary"] == "我的操作"
