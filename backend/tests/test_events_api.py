from datetime import UTC, datetime, timedelta

import pytest

from app.models.order import Signal
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
async def test_list_events_with_signal_and_auto_pause(
    client, auth_headers, db_session, test_user
):
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
async def test_manual_pause_not_exposed_as_auto_pause(
    client, auth_headers, db_session, test_user
):
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
