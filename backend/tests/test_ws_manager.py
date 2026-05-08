"""
WebSocket 连接管理器单元测试 — 注册/订阅/路由/广播
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.ws.manager import Subscription, WSConnectionManager

# ==================== Subscription 数据类 ====================


class TestSubscriptionDataclass:
    def test_defaults(self):
        sub = Subscription()
        assert sub.channels == set()
        assert sub.symbols == set()
        assert sub.ws is None
        assert sub.user_id is None

    def test_explicit_values(self):
        ws = MagicMock()
        sub = Subscription(channels={"ticker"}, symbols={"BTCUSDT"}, ws=ws, user_id="u1")
        assert "ticker" in sub.channels
        assert "BTCUSDT" in sub.symbols
        assert sub.ws is ws
        assert sub.user_id == "u1"


# ==================== 注册 ====================


class TestRegister:
    def setup_method(self):
        self.mgr = WSConnectionManager()

    def test_register_creates_subscription(self):
        ws = MagicMock()
        self.mgr.register("c1", ws)
        assert "c1" in self.mgr._subs
        assert self.mgr._subs["c1"].ws is ws

    def test_register_stores_user_id(self):
        self.mgr.register("c1", MagicMock(), user_id="u42")
        assert self.mgr._subs["c1"].user_id == "u42"

    def test_register_no_user_id_defaults_none(self):
        self.mgr.register("c1", MagicMock())
        assert self.mgr._subs["c1"].user_id is None

    def test_register_multiple_connections(self):
        for i in range(3):
            self.mgr.register(f"c{i}", MagicMock())
        assert len(self.mgr._subs) == 3

    def test_register_stores_client_ip(self):
        self.mgr.register("c1", MagicMock(), client_ip="10.0.0.1")
        assert self.mgr._subs["c1"].client_ip == "10.0.0.1"


# ==================== 连接计数 ====================


class TestConnectionCounts:
    def setup_method(self):
        self.mgr = WSConnectionManager()

    def test_global_count_zero_initial(self):
        assert self.mgr.get_global_connection_count() == 0

    def test_global_count_after_register(self):
        self.mgr.register("c1", MagicMock())
        assert self.mgr.get_global_connection_count() == 1

    def test_user_count(self):
        self.mgr.register("c1", MagicMock(), user_id="u1")
        self.mgr.register("c2", MagicMock(), user_id="u1")
        self.mgr.register("c3", MagicMock(), user_id="u2")
        assert self.mgr.get_user_connection_count("u1") == 2
        assert self.mgr.get_user_connection_count("u2") == 1

    def test_ip_count(self):
        self.mgr.register("c1", MagicMock(), client_ip="1.2.3.4")
        self.mgr.register("c2", MagicMock(), client_ip="1.2.3.4")
        self.mgr.register("c3", MagicMock(), client_ip="5.6.7.8")
        assert self.mgr.get_ip_connection_count("1.2.3.4") == 2
        assert self.mgr.get_ip_connection_count("5.6.7.8") == 1


# ==================== 注销 ====================


class TestUnregister:
    def setup_method(self):
        self.mgr = WSConnectionManager()

    @pytest.mark.asyncio
    async def test_unregister_removes_subscription(self):
        self.mgr.register("c1", MagicMock())
        await self.mgr.unregister("c1")
        assert "c1" not in self.mgr._subs

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_is_noop(self):
        await self.mgr.unregister("nonexistent")  # must not raise

    @pytest.mark.asyncio
    async def test_unregister_cleans_routing_key(self):
        self.mgr.register("c1", MagicMock())
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        assert ("ticker", "BTCUSDT", "spot") in self.mgr._routing

        await self.mgr.unregister("c1")
        assert ("ticker", "BTCUSDT", "spot") not in self.mgr._routing

    @pytest.mark.asyncio
    async def test_unregister_keeps_routing_key_when_other_subscriber_present(self):
        self.mgr.register("c1", MagicMock())
        self.mgr.register("c2", MagicMock())
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        self.mgr.subscribe("c2", ["ticker"], ["BTCUSDT"])

        await self.mgr.unregister("c1")
        assert ("ticker", "BTCUSDT", "spot") in self.mgr._routing
        assert "c2" in self.mgr._routing[("ticker", "BTCUSDT", "spot")]

    @pytest.mark.asyncio
    async def test_unregister_perp_routing_key(self):
        self.mgr.register("c1", MagicMock())
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"], market_type="perp")
        assert ("ticker", "BTCUSDT", "perp") in self.mgr._routing

        await self.mgr.unregister("c1")
        assert ("ticker", "BTCUSDT", "perp") not in self.mgr._routing

    @pytest.mark.asyncio
    async def test_unregister_calls_stop_if_idle_on_proxies(self):
        """issue #9: unregister 后应通知 proxy 停止空闲 stream"""
        mock_proxy = MagicMock()
        mock_proxy.stop_if_idle = AsyncMock()
        self.mgr._proxies["binance"] = mock_proxy

        self.mgr.register("c1", MagicMock())
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])

        await self.mgr.unregister("c1")

        mock_proxy.stop_if_idle.assert_called_once_with("ticker", "BTCUSDT", "spot")


# ==================== 订阅 ====================


class TestSubscribe:
    def setup_method(self):
        self.mgr = WSConnectionManager()
        self.mgr.register("c1", MagicMock())

    def test_subscribe_unknown_conn_id_is_noop(self):
        self.mgr.subscribe("unknown", ["ticker"], ["BTCUSDT"])
        assert ("ticker", "BTCUSDT", "spot") not in self.mgr._routing

    def test_subscribe_adds_routing_entry(self):
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        assert ("ticker", "BTCUSDT", "spot") in self.mgr._routing
        assert "c1" in self.mgr._routing[("ticker", "BTCUSDT", "spot")]

    def test_subscribe_normalises_symbol_to_upper(self):
        self.mgr.subscribe("c1", ["ticker"], ["btcusdt"])
        assert ("ticker", "BTCUSDT", "spot") in self.mgr._routing

    def test_subscribe_multiple_channels_and_symbols(self):
        self.mgr.subscribe("c1", ["ticker", "kline_1m"], ["BTCUSDT", "ETHUSDT"])
        for ch in ("ticker", "kline_1m"):
            for sym in ("BTCUSDT", "ETHUSDT"):
                assert "c1" in self.mgr._routing[(ch, sym, "spot")]

    def test_subscribe_updates_sub_channels_and_symbols(self):
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        sub = self.mgr._subs["c1"]
        assert "ticker" in sub.channels
        assert "BTCUSDT" in sub.symbols

    def test_subscribe_idempotent(self):
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        assert len(self.mgr._routing[("ticker", "BTCUSDT", "spot")]) == 1

    def test_subscribe_perp_market_type(self):
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"], market_type="perp")
        assert ("ticker", "BTCUSDT", "perp") in self.mgr._routing
        assert ("ticker", "BTCUSDT", "spot") not in self.mgr._routing

    def test_subscribe_kline_with_interval(self):
        self.mgr.subscribe("c1", ["kline_5m"], ["BTCUSDT"])
        assert ("kline_5m", "BTCUSDT", "spot") in self.mgr._routing


# ==================== 取消订阅 ====================


class TestUnsubscribe:
    def setup_method(self):
        self.mgr = WSConnectionManager()
        self.mgr.register("c1", MagicMock())
        self.mgr.subscribe("c1", ["ticker", "kline_1m"], ["BTCUSDT"])

    def test_unsubscribe_unknown_conn_id_is_noop(self):
        self.mgr.unsubscribe("unknown", ["ticker"], ["BTCUSDT"])  # no raise

    def test_unsubscribe_removes_routing_key(self):
        self.mgr.unsubscribe("c1", ["ticker"], ["BTCUSDT"])
        assert ("ticker", "BTCUSDT", "spot") not in self.mgr._routing

    def test_unsubscribe_non_subscribed_symbol_is_noop(self):
        self.mgr.unsubscribe("c1", ["ticker"], ["ETHUSDT"])  # never subscribed

    def test_unsubscribe_partial_leaves_other_channels(self):
        self.mgr.unsubscribe("c1", ["ticker"], ["BTCUSDT"])
        assert ("kline_1m", "BTCUSDT", "spot") in self.mgr._routing

    def test_unsubscribe_perp_market_type(self):
        self.mgr.register("c2", MagicMock())
        self.mgr.subscribe("c2", ["ticker"], ["BTCUSDT"], market_type="perp")
        self.mgr.unsubscribe("c2", ["ticker"], ["BTCUSDT"], market_type="perp")
        assert ("ticker", "BTCUSDT", "perp") not in self.mgr._routing


# ==================== get_subscribers ====================


class TestGetSubscribers:
    def setup_method(self):
        self.mgr = WSConnectionManager()

    def test_empty_returns_empty_list(self):
        assert self.mgr.get_subscribers("ticker", "BTCUSDT") == []

    def test_returns_websocket_object(self):
        ws = MagicMock()
        self.mgr.register("c1", ws)
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        assert self.mgr.get_subscribers("ticker", "BTCUSDT") == [ws]

    def test_symbol_lookup_is_case_insensitive(self):
        ws = MagicMock()
        self.mgr.register("c1", ws)
        self.mgr.subscribe("c1", ["ticker"], ["btcusdt"])
        assert self.mgr.get_subscribers("ticker", "BTCUSDT") == [ws]

    def test_skips_subscription_without_ws(self):
        self.mgr._subs["c1"] = Subscription(channels={"ticker"}, symbols={"BTCUSDT"})
        self.mgr._routing[("ticker", "BTCUSDT", "spot")] = {"c1"}
        assert self.mgr.get_subscribers("ticker", "BTCUSDT") == []

    def test_returns_all_subscribers(self):
        for i in range(3):
            ws = MagicMock()
            self.mgr.register(f"c{i}", ws)
            self.mgr.subscribe(f"c{i}", ["ticker"], ["BTCUSDT"])
        assert len(self.mgr.get_subscribers("ticker", "BTCUSDT")) == 3

    def test_perp_market_subscribers_separate(self):
        ws_spot = MagicMock()
        ws_perp = MagicMock()
        self.mgr.register("c_spot", ws_spot)
        self.mgr.register("c_perp", ws_perp)
        self.mgr.subscribe("c_spot", ["ticker"], ["BTCUSDT"], market_type="spot")
        self.mgr.subscribe("c_perp", ["ticker"], ["BTCUSDT"], market_type="perp")

        assert self.mgr.get_subscribers("ticker", "BTCUSDT", "spot") == [ws_spot]
        assert self.mgr.get_subscribers("ticker", "BTCUSDT", "perp") == [ws_perp]


# ==================== has_subscribers ====================


class TestHasSubscribers:
    def setup_method(self):
        self.mgr = WSConnectionManager()

    def test_false_when_no_subscribers(self):
        assert not self.mgr.has_subscribers("ticker", "BTCUSDT")

    def test_true_after_subscribe(self):
        self.mgr.register("c1", MagicMock())
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        assert self.mgr.has_subscribers("ticker", "BTCUSDT")

    @pytest.mark.asyncio
    async def test_false_after_unregister(self):
        self.mgr.register("c1", MagicMock())
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        await self.mgr.unregister("c1")
        assert not self.mgr.has_subscribers("ticker", "BTCUSDT")

    def test_perp_separate_from_spot(self):
        self.mgr.register("c1", MagicMock())
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"], market_type="perp")
        assert not self.mgr.has_subscribers("ticker", "BTCUSDT", "spot")
        assert self.mgr.has_subscribers("ticker", "BTCUSDT", "perp")


# ==================== generate_conn_id ====================


class TestGenerateConnId:
    def test_unique_ids(self):
        mgr = WSConnectionManager()
        ids = {mgr.generate_conn_id() for _ in range(100)}
        assert len(ids) == 100

    def test_prefix_format(self):
        mgr = WSConnectionManager()
        cid = mgr.generate_conn_id()
        assert cid.startswith("conn-")
        assert len(cid) > 5


# ==================== register_proxy ====================


class TestRegisterProxy:
    def test_proxy_stored(self):
        mgr = WSConnectionManager()
        proxy = MagicMock()
        mgr.register_proxy("binance", proxy)
        assert mgr._proxies["binance"] is proxy

    def test_multiple_proxies(self):
        mgr = WSConnectionManager()
        p1, p2 = MagicMock(), MagicMock()
        mgr.register_proxy("binance", p1)
        mgr.register_proxy("okx", p2)
        assert mgr._proxies["binance"] is p1
        assert mgr._proxies["okx"] is p2
