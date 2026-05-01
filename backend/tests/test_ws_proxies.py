"""
WebSocket 交易所代理单元测试 — 消息解析、路由键、广播、任务管理
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.ws.proxies import (
    BinanceWSProxy,
    HuobiProxy,
    OKXProxy,
    PollingFallback,
    _stream_key,
)
from app.core.trade_schemas import WSMessage


# ==================== _stream_key ====================

def test_stream_key_spot():
    assert _stream_key("ticker", "BTCUSDT", "spot") == "ticker:BTCUSDT:spot"


def test_stream_key_perp():
    assert _stream_key("kline", "ETHUSDT", "perp") == "kline:ETHUSDT:perp"


# ==================== BinanceWSProxy._parse_message ====================

class TestBinanceParseMessage:
    def setup_method(self):
        self.proxy = BinanceWSProxy(MagicMock())

    def test_ticker_full(self):
        data = {
            "c": "50000", "p": "100", "P": "0.2",
            "h": "51000", "l": "49000", "v": "1000", "q": "50000000",
        }
        msg = self.proxy._parse_message(data, "ticker", "BTCUSDT")
        assert msg is not None
        assert msg.type == "ticker"
        assert msg.exchange == "binance"
        assert msg.symbol == "BTCUSDT"
        assert msg.data["price"] == "50000"
        assert msg.data["high_24h"] == "51000"

    def test_ticker_missing_c_returns_none(self):
        msg = self.proxy._parse_message({"p": "100"}, "ticker", "BTCUSDT")
        assert msg is None

    def test_kline_full(self):
        data = {"k": {
            "o": "49000", "h": "51000", "l": "48000",
            "c": "50000", "v": "100", "x": True,
        }}
        msg = self.proxy._parse_message(data, "kline", "BTCUSDT")
        assert msg is not None
        assert msg.type == "kline"
        assert msg.data["is_closed"] is True
        assert msg.data["open"] == "49000"

    def test_kline_missing_k_returns_none(self):
        msg = self.proxy._parse_message({"c": "50000"}, "kline", "BTCUSDT")
        assert msg is None

    def test_orderbook_full(self):
        data = {
            "b": [["50000", "1.0"], ["49999", "2.0"]],
            "a": [["50001", "0.5"]],
        }
        msg = self.proxy._parse_message(data, "orderbook", "BTCUSDT")
        assert msg is not None
        assert msg.type == "orderbook"
        assert len(msg.data["bids"]) == 2
        assert msg.data["bids"][0] == {"price": "50000", "quantity": "1.0"}

    def test_orderbook_missing_b_returns_none(self):
        msg = self.proxy._parse_message({"a": []}, "orderbook", "BTCUSDT")
        assert msg is None

    def test_unknown_channel_returns_none(self):
        msg = self.proxy._parse_message({"c": "1"}, "liquidation", "BTCUSDT")
        assert msg is None


# ==================== OKXProxy ====================

class TestOKXToInstId:
    def test_usdt_spot(self):
        assert OKXProxy._to_inst_id("BTCUSDT", "spot") == "BTC-USDT"

    def test_usdt_perp(self):
        assert OKXProxy._to_inst_id("BTCUSDT", "perp") == "BTC-USDT-SWAP"

    def test_usdc_spot(self):
        assert OKXProxy._to_inst_id("ETHUSDC", "spot") == "ETH-USDC"

    def test_usdc_perp(self):
        assert OKXProxy._to_inst_id("ETHUSDC", "perp") == "ETH-USDC-SWAP"

    def test_unknown_symbol_passthrough(self):
        assert OKXProxy._to_inst_id("UNKNOWN", "spot") == "UNKNOWN"


class TestOKXParseMessage:
    def setup_method(self):
        self.proxy = OKXProxy(MagicMock())

    def test_ticker(self):
        data = {
            "arg": {"channel": "tickers"},
            "data": [{
                "last": "50000", "changeUtc24h": "0.5",
                "high24h": "51000", "low24h": "49000",
                "vol24h": "1000", "volCcy24h": "50000000",
            }],
        }
        msg = self.proxy._parse_message(data, "ticker", "BTCUSDT")
        assert msg is not None
        assert msg.type == "ticker"
        assert msg.data["price"] == "50000"
        assert msg.data["high_24h"] == "51000"

    def test_kline(self):
        data = {
            "arg": {"channel": "candle1m"},
            "data": [["1234567890", "49000", "51000", "48000", "50000", "100"]],
        }
        msg = self.proxy._parse_message(data, "kline", "BTCUSDT")
        assert msg is not None
        assert msg.type == "kline"
        assert msg.data["open"] == "49000"
        assert msg.data["close"] == "50000"

    def test_orderbook(self):
        data = {
            "arg": {"channel": "books5"},
            "data": [{"bids": [["50000", "1.0", "0"]], "asks": [["50001", "0.5", "0"]]}],
        }
        msg = self.proxy._parse_message(data, "orderbook", "BTCUSDT")
        assert msg is not None
        assert msg.type == "orderbook"
        assert msg.data["bids"][0]["price"] == "50000"

    def test_empty_data_returns_none(self):
        data = {"arg": {"channel": "tickers"}, "data": []}
        assert self.proxy._parse_message(data, "ticker", "BTCUSDT") is None

    def test_unknown_channel_returns_none(self):
        data = {"arg": {"channel": "trades"}, "data": [{"foo": "bar"}]}
        assert self.proxy._parse_message(data, "ticker", "BTCUSDT") is None


# ==================== HuobiProxy ====================

class TestHuobiToPerpCode:
    def test_usdt(self):
        assert HuobiProxy._to_perp_code("BTCUSDT") == "BTC-USDT"

    def test_usdc(self):
        assert HuobiProxy._to_perp_code("ETHUSDC") == "ETH-USDC"

    def test_unknown_passthrough(self):
        assert HuobiProxy._to_perp_code("SOLBTC") == "SOLBTC"


class TestHuobiParseMessage:
    def setup_method(self):
        self.proxy = HuobiProxy(MagicMock())

    def _ticker_tick(self):
        return {
            "close": 50000, "change": 0.5,
            "high": 51000, "low": 49000, "vol": 1000, "amount": 50000000,
        }

    def test_ticker_via_detail_in_ch(self):
        data = {"ch": "market.btcusdt.detail", "tick": self._ticker_tick()}
        msg = self.proxy._parse_message(data, "ticker", "BTCUSDT")
        assert msg is not None
        assert msg.type == "ticker"
        assert msg.data["price"] == "50000"
        assert msg.data["high_24h"] == "51000"

    def test_ticker_channel_override(self):
        # channel="ticker" matches even without "detail" in ch
        data = {"ch": "market.btcusdt.kline.1min", "tick": self._ticker_tick()}
        msg = self.proxy._parse_message(data, "ticker", "BTCUSDT")
        assert msg is not None
        assert msg.type == "ticker"

    def test_kline(self):
        data = {
            "ch": "market.btcusdt.kline.1min",
            "tick": {"open": 49000, "high": 51000, "low": 48000, "close": 50000, "vol": 100},
        }
        msg = self.proxy._parse_message(data, "kline", "BTCUSDT")
        assert msg is not None
        assert msg.type == "kline"
        assert msg.data["open"] == "49000"

    def test_orderbook(self):
        data = {
            "ch": "market.btcusdt.depth.step0",
            "tick": {"bids": [[50000, 1.0], [49999, 2.0]], "asks": [[50001, 0.5]]},
        }
        msg = self.proxy._parse_message(data, "orderbook", "BTCUSDT")
        assert msg is not None
        assert msg.type == "orderbook"
        assert len(msg.data["bids"]) == 2

    def test_empty_tick_returns_none(self):
        data = {"ch": "market.btcusdt.detail", "tick": {}}
        assert self.proxy._parse_message(data, "ticker", "BTCUSDT") is None


# ==================== ExchangeWSProxy._broadcast ====================

class TestBroadcast:
    async def test_sends_to_all_subscribers(self):
        ws1, ws2 = AsyncMock(), AsyncMock()
        mock_mgr = MagicMock()
        mock_mgr.get_subscribers.return_value = [ws1, ws2]

        proxy = BinanceWSProxy(mock_mgr)
        msg = WSMessage(type="ticker", exchange="binance", symbol="BTCUSDT", data={})
        await proxy._broadcast(msg)

        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()
        # verify it's called with valid JSON
        call_arg = ws1.send_text.call_args[0][0]
        assert "ticker" in call_arg

    async def test_continues_after_send_error(self):
        ws1, ws2 = AsyncMock(), AsyncMock()
        ws1.send_text.side_effect = Exception("broken pipe")
        mock_mgr = MagicMock()
        mock_mgr.get_subscribers.return_value = [ws1, ws2]

        proxy = BinanceWSProxy(mock_mgr)
        msg = WSMessage(type="ticker", exchange="binance", symbol="BTCUSDT", data={})
        await proxy._broadcast(msg)  # must not raise

        ws2.send_text.assert_called_once()

    async def test_empty_subscribers_no_send(self):
        mock_mgr = MagicMock()
        mock_mgr.get_subscribers.return_value = []
        proxy = BinanceWSProxy(mock_mgr)
        msg = WSMessage(type="ticker", exchange="binance", symbol="BTCUSDT", data={})
        await proxy._broadcast(msg)  # no calls, no errors


# ==================== start_if_needed / stop_if_idle ====================

class TestStartStopProxy:
    async def test_start_if_needed_creates_task_when_has_subscribers(self, monkeypatch):
        mock_mgr = MagicMock()
        mock_mgr.has_subscribers.return_value = True
        proxy = BinanceWSProxy(mock_mgr)

        task = MagicMock(spec=asyncio.Task)
        monkeypatch.setattr(asyncio, "create_task", lambda coro, **kw: task)

        await proxy.start_if_needed("ticker", "BTCUSDT", "spot")
        assert "ticker:BTCUSDT:spot" in proxy._tasks

    async def test_start_if_needed_idempotent(self, monkeypatch):
        mock_mgr = MagicMock()
        mock_mgr.has_subscribers.return_value = True
        proxy = BinanceWSProxy(mock_mgr)

        call_count = []
        task = MagicMock(spec=asyncio.Task)
        monkeypatch.setattr(asyncio, "create_task", lambda coro, **kw: (call_count.append(1), task)[1])

        await proxy.start_if_needed("ticker", "BTCUSDT", "spot")
        await proxy.start_if_needed("ticker", "BTCUSDT", "spot")
        assert len(call_count) == 1

    async def test_start_if_needed_noop_when_no_subscribers(self, monkeypatch):
        mock_mgr = MagicMock()
        mock_mgr.has_subscribers.return_value = False
        proxy = BinanceWSProxy(mock_mgr)

        created = []
        monkeypatch.setattr(asyncio, "create_task", lambda coro, **kw: created.append(1))

        await proxy.start_if_needed("ticker", "BTCUSDT", "spot")
        assert created == []

    async def test_stop_if_idle_cancels_task(self):
        mock_mgr = MagicMock()
        mock_mgr.has_subscribers.return_value = False
        proxy = BinanceWSProxy(mock_mgr)

        task = MagicMock(spec=asyncio.Task)
        proxy._tasks["ticker:BTCUSDT:spot"] = task

        await proxy.stop_if_idle("ticker", "BTCUSDT", "spot")

        task.cancel.assert_called_once()
        assert "ticker:BTCUSDT:spot" not in proxy._tasks

    async def test_stop_if_idle_keeps_task_with_active_subscribers(self):
        mock_mgr = MagicMock()
        mock_mgr.has_subscribers.return_value = True
        proxy = BinanceWSProxy(mock_mgr)

        task = MagicMock(spec=asyncio.Task)
        proxy._tasks["ticker:BTCUSDT:spot"] = task

        await proxy.stop_if_idle("ticker", "BTCUSDT", "spot")
        task.cancel.assert_not_called()


# ==================== _restart_on_error ====================

class TestRestartOnError:
    async def test_sleeps_5s_then_restarts_when_has_subscribers(self, monkeypatch):
        slept = []

        async def mock_sleep(delay):
            slept.append(delay)

        monkeypatch.setattr(asyncio, "sleep", mock_sleep)

        mock_mgr = MagicMock()
        mock_mgr.has_subscribers.return_value = True

        task = MagicMock(spec=asyncio.Task)
        monkeypatch.setattr(asyncio, "create_task", lambda coro, **kw: task)

        proxy = BinanceWSProxy(mock_mgr)
        await proxy._restart_on_error("ticker", "BTCUSDT", "spot")

        assert slept == [5]
        assert "ticker:BTCUSDT:spot" in proxy._tasks

    async def test_no_restart_when_no_subscribers(self, monkeypatch):
        async def mock_sleep(delay):
            pass

        monkeypatch.setattr(asyncio, "sleep", mock_sleep)

        mock_mgr = MagicMock()
        mock_mgr.has_subscribers.return_value = False

        created = []
        monkeypatch.setattr(asyncio, "create_task", lambda coro, **kw: created.append(1))

        proxy = BinanceWSProxy(mock_mgr)
        await proxy._restart_on_error("ticker", "BTCUSDT", "spot")
        assert created == []


# ==================== PollingFallback ====================

class TestPollingFallback:
    async def test_start_sets_running_and_creates_task(self, monkeypatch):
        mock_mgr = MagicMock()
        mock_mgr._subs = {}
        fallback = PollingFallback(mock_mgr)

        task = MagicMock(spec=asyncio.Task)
        monkeypatch.setattr(asyncio, "create_task", lambda coro, **kw: task)

        await fallback.start()
        assert fallback._running is True
        assert "polling" in fallback._tasks

    async def test_start_idempotent_when_already_running(self, monkeypatch):
        mock_mgr = MagicMock()
        fallback = PollingFallback(mock_mgr)
        fallback._running = True

        created = []
        monkeypatch.setattr(asyncio, "create_task", lambda coro, **kw: created.append(1))

        await fallback.start()
        assert created == []

    async def test_stop_cancels_all_tasks(self):
        mock_mgr = MagicMock()
        fallback = PollingFallback(mock_mgr)

        task = MagicMock(spec=asyncio.Task)
        fallback._tasks["polling"] = task
        fallback._running = True

        await fallback.stop()

        task.cancel.assert_called_once()
        assert fallback._running is False
