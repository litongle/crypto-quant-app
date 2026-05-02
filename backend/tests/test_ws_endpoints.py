"""
WebSocket endpoint 单元测试 — 心跳与消息格式
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.ws.endpoints import (
    _is_pong_message,
    _parse_subprotocols,
    _probe_heartbeat,
    _read_auth_token,
    _read_protocol_token,
    _select_accept_subprotocol,
)


def test_is_pong_message_accepts_action_and_type():
    assert _is_pong_message('{"action":"pong"}') is True
    assert _is_pong_message('{"type":"pong","data":{}}') is True
    assert _is_pong_message('{"action":"ping"}') is False
    assert _is_pong_message("not-json") is False


def test_parse_subprotocols_and_extract_protocol_token():
    websocket = MagicMock()
    websocket.headers = {
        "sec-websocket-protocol": "json, access_token.jwt.part, trace-v1",
    }

    assert _parse_subprotocols(websocket) == [
        "json",
        "access_token.jwt.part",
        "trace-v1",
    ]
    assert _read_protocol_token(websocket) == "jwt.part"
    assert _select_accept_subprotocol(websocket) == "json"


@pytest.mark.asyncio
async def test_read_auth_token_prefers_protocol_token_over_legacy_message():
    websocket = MagicMock()
    websocket.headers = {
        "authorization": "",
        "sec-websocket-protocol": "json, access_token.jwt.part",
    }
    websocket.receive_text = AsyncMock(return_value='{"action":"auth","token":"legacy"}')

    token = await _read_auth_token(websocket)

    assert token == "jwt.part"
    websocket.receive_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_probe_heartbeat_sends_ping_and_accepts_pong():
    websocket = MagicMock()
    websocket.send_text = AsyncMock()
    websocket.receive_text = AsyncMock(return_value='{"action":"pong"}')
    websocket.close = AsyncMock()

    ok = await _probe_heartbeat(websocket, "conn-1")

    assert ok == (True, None)
    websocket.send_text.assert_awaited_once()
    sent_payload = websocket.send_text.await_args.args[0]
    assert '"type":"ping"' in sent_payload
    websocket.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_probe_heartbeat_closes_connection_when_pong_missing():
    websocket = MagicMock()
    websocket.send_text = AsyncMock()
    websocket.receive_text = AsyncMock(return_value='{"action":"subscribe"}')
    websocket.close = AsyncMock()

    ok = await _probe_heartbeat(websocket, "conn-2")

    assert ok == (True, '{"action":"subscribe"}')
    websocket.send_text.assert_awaited_once()
    websocket.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_probe_heartbeat_closes_connection_when_client_silent():
    websocket = MagicMock()
    websocket.send_text = AsyncMock()
    websocket.receive_text = AsyncMock(side_effect=TimeoutError)
    websocket.close = AsyncMock()

    ok = await _probe_heartbeat(websocket, "conn-3")

    assert ok == (False, None)
    websocket.send_text.assert_awaited_once()
    websocket.close.assert_awaited_once_with(code=4000, reason="Heartbeat timeout")
