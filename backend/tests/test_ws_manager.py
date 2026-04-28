"""
WebSocket 连接管理器单元测试 — 注册/订阅/路由/广播
"""
from unittest.mock import MagicMock

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


# ==================== 注销 ====================

class TestUnregister:
    def setup_method(self):
        self.mgr = WSConnectionManager()

    def test_unregister_removes_subscription(self):
        self.mgr.register("c1", MagicMock())
        self.mgr.unregister("c1")
        assert "c1" not in self.mgr._subs

    def test_unregister_nonexistent_is_noop(self):
        self.mgr.unregister("nonexistent")  # must not raise

    def test_unregister_cleans_routing_key(self):
        self.mgr.register("c1", MagicMock())
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        assert ("ticker", "BTCUSDT") in self.mgr._routing

        self.mgr.unregister("c1")
        assert ("ticker", "BTCUSDT") not in self.mgr._routing

    def test_unregister_keeps_routing_key_when_other_subscriber_present(self):
        self.mgr.register("c1", MagicMock())
        self.mgr.register("c2", MagicMock())
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        self.mgr.subscribe("c2", ["ticker"], ["BTCUSDT"])

        self.mgr.unregister("c1")
        assert ("ticker", "BTCUSDT") in self.mgr._routing
        assert "c2" in self.mgr._routing[("ticker", "BTCUSDT")]


# ==================== 订阅 ====================

class TestSubscribe:
    def setup_method(self):
        self.mgr = WSConnectionManager()
        self.mgr.register("c1", MagicMock())

    def test_subscribe_unknown_conn_id_is_noop(self):
        self.mgr.subscribe("unknown", ["ticker"], ["BTCUSDT"])
        assert ("ticker", "BTCUSDT") not in self.mgr._routing

    def test_subscribe_adds_routing_entry(self):
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        assert ("ticker", "BTCUSDT") in self.mgr._routing
        assert "c1" in self.mgr._routing[("ticker", "BTCUSDT")]

    def test_subscribe_normalises_symbol_to_upper(self):
        self.mgr.subscribe("c1", ["ticker"], ["btcusdt"])
        assert ("ticker", "BTCUSDT") in self.mgr._routing

    def test_subscribe_multiple_channels_and_symbols(self):
        self.mgr.subscribe("c1", ["ticker", "kline"], ["BTCUSDT", "ETHUSDT"])
        for ch in ("ticker", "kline"):
            for sym in ("BTCUSDT", "ETHUSDT"):
                assert ("c1" in self.mgr._routing[(ch, sym)])

    def test_subscribe_updates_sub_channels_and_symbols(self):
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        sub = self.mgr._subs["c1"]
        assert "ticker" in sub.channels
        assert "BTCUSDT" in sub.symbols

    def test_subscribe_idempotent(self):
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        assert len(self.mgr._routing[("ticker", "BTCUSDT")]) == 1


# ==================== 取消订阅 ====================

class TestUnsubscribe:
    def setup_method(self):
        self.mgr = WSConnectionManager()
        self.mgr.register("c1", MagicMock())
        self.mgr.subscribe("c1", ["ticker", "kline"], ["BTCUSDT"])

    def test_unsubscribe_unknown_conn_id_is_noop(self):
        self.mgr.unsubscribe("unknown", ["ticker"], ["BTCUSDT"])  # no raise

    def test_unsubscribe_removes_routing_key(self):
        self.mgr.unsubscribe("c1", ["ticker"], ["BTCUSDT"])
        assert ("ticker", "BTCUSDT") not in self.mgr._routing

    def test_unsubscribe_non_subscribed_symbol_is_noop(self):
        self.mgr.unsubscribe("c1", ["ticker"], ["ETHUSDT"])  # never subscribed

    def test_unsubscribe_partial_leaves_other_channels(self):
        self.mgr.unsubscribe("c1", ["ticker"], ["BTCUSDT"])
        assert ("kline", "BTCUSDT") in self.mgr._routing


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
        self.mgr._routing[("ticker", "BTCUSDT")] = {"c1"}
        assert self.mgr.get_subscribers("ticker", "BTCUSDT") == []

    def test_returns_all_subscribers(self):
        for i in range(3):
            ws = MagicMock()
            self.mgr.register(f"c{i}", ws)
            self.mgr.subscribe(f"c{i}", ["ticker"], ["BTCUSDT"])
        assert len(self.mgr.get_subscribers("ticker", "BTCUSDT")) == 3


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

    def test_false_after_unregister(self):
        self.mgr.register("c1", MagicMock())
        self.mgr.subscribe("c1", ["ticker"], ["BTCUSDT"])
        self.mgr.unregister("c1")
        assert not self.mgr.has_subscribers("ticker", "BTCUSDT")


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
