"""
统一交易/行情响应结构封装

所有前端交互的 schema 统一定义在这，确保：
1. REST API 和 WebSocket 推送使用同一套结构
2. 不同交易所返回的字段名完全一致
3. Decimal 统一序列化为 str（精度安全）
4. 时间统一 ISO 8601 格式
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_serializer


# ==================== 工具 ====================

def _dt_to_iso(dt: datetime | None) -> str | None:
    """datetime → ISO 8601 字符串"""
    if dt is None:
        return None
    return dt.isoformat()


def _dec_to_str(v: Decimal | None) -> str | None:
    """Decimal → 字符串（前端不丢精度）"""
    if v is None:
        return None
    return str(v)


# ==================== 行情 ====================

class TickerSchema(BaseModel):
    """统一行情结构"""
    symbol: str
    price: str
    price_change: str
    price_change_percent: str
    high_24h: str
    low_24h: str
    volume_24h: str
    quote_volume_24h: str
    timestamp: str  # ISO 8601

    @classmethod
    def from_dataclass(cls, t: Any) -> "TickerSchema":
        """从 exchange_adapter.Ticker 转换"""
        return cls(
            symbol=t.symbol,
            price=str(t.price),
            price_change=str(t.price_change),
            price_change_percent=str(t.price_change_percent),
            high_24h=str(t.high_24h),
            low_24h=str(t.low_24h),
            volume_24h=str(t.volume_24h),
            quote_volume_24h=str(t.quote_volume_24h),
            timestamp=_dt_to_iso(t.timestamp),
        )


class KlineSchema(BaseModel):
    """统一K线结构"""
    timestamp: str
    open: str
    high: str
    low: str
    close: str
    volume: str
    close_time: str

    @classmethod
    def from_dataclass(cls, k: Any) -> "KlineSchema":
        return cls(
            timestamp=_dt_to_iso(k.timestamp),
            open=str(k.open),
            high=str(k.high),
            low=str(k.low),
            close=str(k.close),
            volume=str(k.volume),
            close_time=_dt_to_iso(k.close_time),
        )


class OrderBookEntrySchema(BaseModel):
    """订单簿条目"""
    price: str
    quantity: str


class OrderBookSchema(BaseModel):
    """统一订单簿结构"""
    bids: list[OrderBookEntrySchema]
    asks: list[OrderBookEntrySchema]

    @classmethod
    def from_dataclass(cls, ob: Any) -> "OrderBookSchema":
        return cls(
            bids=[OrderBookEntrySchema(price=str(p), quantity=str(q)) for p, q in ob.bids],
            asks=[OrderBookEntrySchema(price=str(p), quantity=str(q)) for p, q in ob.asks],
        )


# ==================== 账户/余额 ====================

class BalanceSchema(BaseModel):
    """统一余额结构"""
    asset: str
    free: str
    locked: str

    @classmethod
    def from_dataclass(cls, b: Any) -> "BalanceSchema":
        return cls(asset=b.asset, free=str(b.free), locked=str(b.locked))


class AccountInfoSchema(BaseModel):
    """统一账户信息"""
    id: int
    exchange: str
    account_name: str
    is_active: bool
    is_demo: bool = False
    is_testnet: bool = False
    status: str
    balance: str = "0"
    frozen_balance: str = "0"
    error_message: str | None = None
    last_sync_at: str | None = None

    @classmethod
    def from_model(cls, a: Any) -> "AccountInfoSchema":
        return cls(
            id=a.id,
            exchange=a.exchange,
            account_name=a.account_name,
            is_active=a.is_active,
            is_demo=getattr(a, "is_demo", False),
            is_testnet=getattr(a, "is_testnet", False),
            status=a.status,
            balance=str(getattr(a, "balance", 0)),
            frozen_balance=str(getattr(a, "frozen_balance", 0)),
            error_message=getattr(a, "error_message", None),
            last_sync_at=_dt_to_iso(getattr(a, "last_sync_at", None)),
        )


# ==================== 订单 ====================

class OrderResultSchema(BaseModel):
    """统一订单结果（交易所返回）"""
    exchange_order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    quantity: str
    price: str | None = None
    status: str
    filled_quantity: str = "0"
    avg_fill_price: str | None = None

    @classmethod
    def from_dataclass(cls, r: Any) -> "OrderResultSchema":
        return cls(
            exchange_order_id=r.exchange_order_id,
            symbol=r.symbol,
            side=r.side,
            order_type=r.order_type,
            quantity=str(r.quantity),
            price=str(r.price) if r.price is not None else None,
            status=r.status,
            filled_quantity=str(r.filled_quantity),
            avg_fill_price=str(r.avg_fill_price) if r.avg_fill_price is not None else None,
        )


class OrderSchema(BaseModel):
    """统一订单结构（数据库 Order → 前端）

    这是前端看到的最完整的订单信息，包含了：
    - 订单基础信息（symbol/side/type/quantity/price）
    - 交易所状态（exchange_order_id/status/filled_quantity/avg_fill_price）
    - 策略来源（strategy_instance_id）
    - 错误信息（error_message）
    - 时间线（created_at/submitted_at/filled_at/cancelled_at）
    """
    id: int
    account_id: int
    exchange_order_id: str | None = None
    symbol: str
    side: str
    order_type: str
    quantity: str
    price: str | None = None
    filled_quantity: str = "0"
    avg_fill_price: str | None = None
    order_value: str = "0"
    commission: str = "0"
    pnl: str | None = None
    status: str
    strategy_instance_id: int | None = None
    error_message: str | None = None
    created_at: str | None = None
    submitted_at: str | None = None
    filled_at: str | None = None
    cancelled_at: str | None = None

    @classmethod
    def from_model(cls, o: Any) -> "OrderSchema":
        return cls(
            id=o.id,
            account_id=o.account_id,
            exchange_order_id=o.exchange_order_id,
            symbol=o.symbol,
            side=o.side,
            order_type=o.order_type,
            quantity=str(o.quantity),
            price=str(o.price) if o.price is not None else None,
            filled_quantity=str(getattr(o, "filled_quantity", 0)),
            avg_fill_price=str(o.avg_fill_price) if getattr(o, "avg_fill_price", None) is not None else None,
            order_value=str(getattr(o, "order_value", 0)),
            commission=str(getattr(o, "commission", 0)),
            pnl=str(o.pnl) if getattr(o, "pnl", None) is not None else None,
            status=o.status,
            strategy_instance_id=o.strategy_instance_id,
            error_message=o.error_message,
            created_at=_dt_to_iso(o.created_at),
            submitted_at=_dt_to_iso(getattr(o, "submitted_at", None)),
            filled_at=_dt_to_iso(getattr(o, "filled_at", None)),
            cancelled_at=_dt_to_iso(getattr(o, "cancelled_at", None)),
        )


# ==================== 持仓 ====================

class PositionSchema(BaseModel):
    """统一持仓结构"""
    id: int
    account_id: int
    symbol: str
    side: str
    quantity: str
    entry_price: str
    current_price: str
    unrealized_pnl: str = "0"
    unrealized_pnl_percent: str = "0"
    leverage: int = 1
    stop_loss_price: str | None = None
    take_profit_price: str | None = None
    status: str
    strategy_instance_id: int | None = None
    opened_at: str | None = None
    closed_at: str | None = None

    @classmethod
    def from_model(cls, p: Any) -> "PositionSchema":
        return cls(
            id=p.id,
            account_id=p.account_id,
            symbol=p.symbol,
            side=p.side,
            quantity=str(p.quantity),
            entry_price=str(p.entry_price),
            current_price=str(p.current_price),
            unrealized_pnl=str(getattr(p, "unrealized_pnl", 0)),
            unrealized_pnl_percent=str(getattr(p, "unrealized_pnl_percent", 0)),
            leverage=getattr(p, "leverage", 1),
            stop_loss_price=str(p.stop_loss_price) if p.stop_loss_price is not None else None,
            take_profit_price=str(p.take_profit_price) if p.take_profit_price is not None else None,
            status=p.status,
            strategy_instance_id=p.strategy_instance_id,
            opened_at=_dt_to_iso(getattr(p, "opened_at", None)),
            closed_at=_dt_to_iso(getattr(p, "closed_at", None)),
        )


class PositionResultSchema(BaseModel):
    """统一持仓信息（交易所返回）"""
    symbol: str
    side: str
    quantity: str
    entry_price: str
    current_price: str
    unrealized_pnl: str
    leverage: int

    @classmethod
    def from_dataclass(cls, p: Any) -> "PositionResultSchema":
        return cls(
            symbol=p.symbol,
            side=p.side,
            quantity=str(p.quantity),
            entry_price=str(p.entry_price),
            current_price=str(p.current_price),
            unrealized_pnl=str(p.unrealized_pnl),
            leverage=p.leverage,
        )


# ==================== WebSocket 推送消息 ====================

class WSMessage(BaseModel):
    """WebSocket 推送消息的统一信封"""
    type: str = Field(description="消息类型: ticker/kline/orderbook/order/balance/position/error/pong")
    data: Any = Field(description="消息体")
    exchange: str | None = Field(default=None, description="交易所来源")
    symbol: str | None = Field(default=None, description="交易对")
    timestamp: str = Field(default="", description="推送时间 ISO 8601")

    def __init__(self, **data: Any):
        super().__init__(**data)
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()
