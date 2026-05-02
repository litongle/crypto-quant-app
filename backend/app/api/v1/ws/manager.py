"""
WebSocket 订阅管理器
"""

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

MAX_GLOBAL_CONNECTIONS = 1000
MAX_CONNECTIONS_PER_USER = 5
MAX_CONNECTIONS_PER_IP = 20


@dataclass
class Subscription:
    """单个 WebSocket 连接的订阅信息"""

    channels: set[str] = field(default_factory=set)
    symbols: set[str] = field(default_factory=set)
    market_types: set[str] = field(default_factory=set)
    ws: WebSocket | None = None
    user_id: str | None = None
    client_ip: str | None = None


class WSConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self._subs: dict[str, Subscription] = {}
        self._routing: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        self._proxies: dict[str, Any] = {}

    @staticmethod
    def generate_conn_id() -> str:
        """生成唯一的连接 ID"""
        return f"conn-{uuid.uuid4().hex}"

    def get_global_connection_count(self) -> int:
        """获取全局连接数"""
        return len(self._subs)

    def get_user_connection_count(self, user_id: str) -> int:
        """获取指定用户的连接数"""
        return sum(1 for sub in self._subs.values() if sub.user_id == user_id)

    def get_ip_connection_count(self, client_ip: str) -> int:
        """获取指定 IP 的连接数"""
        return sum(1 for sub in self._subs.values() if sub.client_ip == client_ip)

    def register(
        self, conn_id: str, ws: WebSocket, user_id: str | None = None, client_ip: str | None = None
    ) -> None:
        self._subs[conn_id] = Subscription(ws=ws, user_id=user_id, client_ip=client_ip)
        logger.info(
            "[WSManager] 连接注册: %s (user=%s, ip=%s), 当前连接数: %d",
            conn_id,
            user_id,
            client_ip,
            len(self._subs),
        )

    async def unregister(self, conn_id: str) -> Subscription | None:
        sub = self._subs.pop(conn_id, None)
        if sub:
            for channel in sub.channels:
                for symbol in sub.symbols:
                    for market_type in sub.market_types:
                        key = (channel, symbol, market_type)
                        self._routing[key].discard(conn_id)
                        if not self._routing[key]:
                            del self._routing[key]
            # 通知所有 proxy 停止空闲 stream（issue #9）
            for proxy in self._proxies.values():
                if hasattr(proxy, "stop_if_idle"):
                    for channel in sub.channels:
                        for symbol in sub.symbols:
                            for market_type in sub.market_types:
                                await proxy.stop_if_idle(channel, symbol, market_type)
            logger.info("[WSManager] 连接注销: %s, 剩余连接数: %d", conn_id, len(self._subs))
            return sub
        return None

    def subscribe(
        self, conn_id: str, channels: list[str], symbols: list[str], market_type: str = "spot"
    ) -> None:
        sub = self._subs.get(conn_id)
        if not sub:
            return
        for ch in channels:
            sub.channels.add(ch)
            sub.market_types.add(market_type)
            for sym in symbols:
                sym_upper = sym.upper()
                sub.symbols.add(sym_upper)
                self._routing[(ch, sym_upper, market_type)].add(conn_id)
        logger.info(
            "[WSManager] 订阅: conn=%s, channels=%s, symbols=%s, market=%s",
            conn_id,
            channels,
            symbols,
            market_type,
        )

    def unsubscribe(
        self, conn_id: str, channels: list[str], symbols: list[str], market_type: str = "spot"
    ) -> None:
        sub = self._subs.get(conn_id)
        if not sub:
            return
        for ch in channels:
            for sym in symbols:
                sym_upper = sym.upper()
                key = (ch, sym_upper, market_type)
                self._routing[key].discard(conn_id)
                if not self._routing[key]:
                    del self._routing[key]
        logger.info(
            "[WSManager] 取消订阅: conn=%s, channels=%s, symbols=%s, market=%s",
            conn_id,
            channels,
            symbols,
            market_type,
        )

    def get_subscribers(
        self, channel: str, symbol: str, market_type: str = "spot"
    ) -> list[WebSocket]:
        conn_ids = self._routing.get((channel, symbol.upper(), market_type), set())
        result = []
        for cid in conn_ids:
            sub = self._subs.get(cid)
            if sub and sub.ws:
                result.append(sub.ws)
        return result

    def has_subscribers(self, channel: str, symbol: str, market_type: str = "spot") -> bool:
        return bool(self._routing.get((channel, symbol.upper(), market_type)))

    def register_proxy(self, exchange: str, proxy: Any) -> None:
        self._proxies[exchange] = proxy


manager = WSConnectionManager()
