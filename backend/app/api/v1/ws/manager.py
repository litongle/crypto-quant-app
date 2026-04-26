"""
WebSocket 订阅管理器
"""
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from fastapi import WebSocket

logger = logging.getLogger(__name__)

@dataclass
class Subscription:
    """单个 WebSocket 连接的订阅信息"""
    channels: set[str] = field(default_factory=set)
    symbols: set[str] = field(default_factory=set)
    ws: WebSocket | None = None
    user_id: str | None = None

class WSConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self._subs: dict[str, Subscription] = {}
        self._routing: dict[tuple[str, str], set[str]] = defaultdict(set)
        self._proxies: dict[str, Any] = {}

    def register(self, conn_id: str, ws: WebSocket, user_id: str | None = None) -> None:
        self._subs[conn_id] = Subscription(ws=ws, user_id=user_id)
        logger.info("[WSManager] 连接注册: %s (user=%s), 当前连接数: %d", conn_id, user_id, len(self._subs))

    def unregister(self, conn_id: str) -> None:
        sub = self._subs.pop(conn_id, None)
        if sub:
            for channel in sub.channels:
                for symbol in sub.symbols:
                    key = (channel, symbol)
                    self._routing[key].discard(conn_id)
                    if not self._routing[key]:
                        del self._routing[key]
            logger.info("[WSManager] 连接注销: %s, 剩余连接数: %d", conn_id, len(self._subs))

    def subscribe(self, conn_id: str, channels: list[str], symbols: list[str]) -> None:
        sub = self._subs.get(conn_id)
        if not sub:
            return
        for ch in channels:
            sub.channels.add(ch)
            for sym in symbols:
                sym_upper = sym.upper()
                sub.symbols.add(sym_upper)
                self._routing[(ch, sym_upper)].add(conn_id)
        logger.info("[WSManager] 订阅: conn=%s, channels=%s, symbols=%s", conn_id, channels, symbols)

    def unsubscribe(self, conn_id: str, channels: list[str], symbols: list[str]) -> None:
        sub = self._subs.get(conn_id)
        if not sub:
            return
        for ch in channels:
            for sym in symbols:
                sym_upper = sym.upper()
                key = (ch, sym_upper)
                self._routing[key].discard(conn_id)
                if not self._routing[key]:
                    del self._routing[key]
        logger.info("[WSManager] 取消订阅: conn=%s, channels=%s, symbols=%s", conn_id, channels, symbols)

    def get_subscribers(self, channel: str, symbol: str) -> list[WebSocket]:
        conn_ids = self._routing.get((channel, symbol.upper()), set())
        result = []
        for cid in conn_ids:
            sub = self._subs.get(cid)
            if sub and sub.ws:
                result.append(sub.ws)
        return result

    def has_subscribers(self, channel: str, symbol: str) -> bool:
        return bool(self._routing.get((channel, symbol.upper())))

    def register_proxy(self, exchange: str, proxy: Any) -> None:
        self._proxies[exchange] = proxy

from typing import Any
manager = WSConnectionManager()
