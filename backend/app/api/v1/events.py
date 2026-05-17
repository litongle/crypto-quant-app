"""事件流 API — 聚合交易信号与策略自停事件（单用户版，不再依赖审计日志）。"""

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.schemas import APIResponse
from app.database import get_session
from app.models.audit_event import AuditEvent
from app.models.exchange import ExchangeAccount
from app.models.order import Order, Signal
from app.models.strategy import StrategyInstance
from app.models.user import User

router = APIRouter()

EventType = Literal["signal", "order", "auto_pause", "risk_alert", "user_action", "system"]
Severity = Literal["info", "warning", "error", "critical"]

_ORDER_STATUS_LABEL = {
    "pending": "待提交",
    "submitted": "已提交",
    "partial": "部分成交",
    "filled": "已成交",
    "cancelled": "已撤销",
    "rejected": "已拒单",
}

_ORDER_SIDE_LABEL = {"buy": "买入", "sell": "卖出"}

# RSI 策略 reason 枚举 → 中文标签
# DB 里 signal.reason 保持英文 enum（保留机器可读性，方便后续过滤/统计），
# 仅在 summary 展示层翻译。识别不到的 reason 会走兜底分支保留原文。
_RSI_EVENT_LABEL = {
    "LONG_OPEN": "多头开仓",
    "SHORT_OPEN": "空头开仓",
    "LONG_ADD": "多头加仓",
    "SHORT_ADD": "空头加仓",
    "TAKE_PROFIT_LONG": "多头止盈",
    "TAKE_PROFIT_SHORT": "空头止盈",
    "STOP_LOSS_LONG": "多头止损",
    "STOP_LOSS_SHORT": "空头止损",
    "REVERSE_LONG_TO_SHORT": "多翻空",
    "REVERSE_SHORT_TO_LONG": "空翻多",
    "TIMEOUT_LONG": "多头超时平仓",
    "TIMEOUT_SHORT": "空头超时平仓",
}

_RSI_REASON_PATTERN = re.compile(
    r"^RSI_(?P<event>[A-Z_]+?)"
    r"(?:\s+rsi=(?P<rsi>-?\d+(?:\.\d+)?))?"
    r"(?:\s+count=(?P<count>\d+))?"
    r"(?:\s+holding=(?P<holding>\d+))?\s*$"
)

_AUTO_PAUSE_REASON_LABEL = {
    "auto:heartbeat_timeout": "心跳超时",
    "auto:consecutive_errors": "连续错误",
    "auto:order_failures": "下单失败次数过多",
    "auto:state_drift": "持仓状态漂移",
    "auto:unknown": "未知原因",
}


def _isoformat(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat().replace("+00:00", "Z")


def _format_price(value: Decimal | None) -> str:
    """Decimal 价格去尾随零（2283.50000000 → 2283.5），整数去掉小数点。"""
    if value is None:
        return ""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _translate_rsi_reason(reason: str | None) -> tuple[str, str] | None:
    """解析 RSI_* 枚举 reason，返回 (中文标签, 数值后缀)；识别不到返回 None。"""
    if not reason:
        return None
    match = _RSI_REASON_PATTERN.match(reason)
    if not match:
        return None
    label = _RSI_EVENT_LABEL.get(match.group("event"))
    if label is None:
        return None
    count = match.group("count")
    if count is not None:
        label = f"{label} #{count}"
    suffix_parts: list[str] = []
    rsi_value = match.group("rsi")
    if rsi_value is not None:
        suffix_parts.append(f"RSI {rsi_value}")
    holding = match.group("holding")
    if holding is not None:
        suffix_parts.append(f"持仓 {holding} 根")
    return label, " · ".join(suffix_parts)


def _serialize_signal(signal: Signal, related_order: Order | None = None) -> dict[str, Any]:
    price_str = _format_price(signal.entry_price)
    price = f" @ {price_str}" if price_str else ""
    translated = _translate_rsi_reason(signal.reason)
    if translated is not None:
        label, suffix = translated
        suffix_part = f" · {suffix}" if suffix else ""
        summary = f"{signal.symbol} {label}{price}{suffix_part}"
    else:
        action_map = {"buy": "买入", "sell": "卖出", "close": "平仓"}
        action_label = action_map.get(signal.action, signal.action)
        reason_part = f" · {signal.reason}" if signal.reason else ""
        summary = f"{signal.symbol} {action_label}{price}{reason_part}"

    detail: dict[str, Any] = {
        "symbol": signal.symbol,
        "action": signal.action,
        "status": signal.status,
        "reason": signal.reason,
    }
    if signal.entry_price is not None:
        detail["entry_price"] = _format_price(signal.entry_price)
    if related_order is not None:
        detail["order_id"] = related_order.id
        detail["order_status"] = related_order.status
        if related_order.avg_fill_price is not None:
            fill_price_str = _format_price(related_order.avg_fill_price)
            detail["fill_price"] = fill_price_str
            # 滑点：(fill - signal_entry) / signal_entry, sell 反向
            if signal.entry_price and signal.entry_price > 0:
                slippage = (related_order.avg_fill_price - signal.entry_price) / signal.entry_price
                if signal.action == "sell":
                    slippage = -slippage
                detail["slippage_pct"] = f"{slippage * 100:.4f}"

    return {
        "id": f"signal:{signal.id}",
        "at": _isoformat(signal.created_at),
        "type": "signal",
        "severity": _signal_severity(signal),
        "instance_id": signal.strategy_instance_id,
        "summary": summary[:200],
        "detail": detail,
    }


def _serialize_order(order: Order) -> dict[str, Any]:
    status_label = _ORDER_STATUS_LABEL.get(order.status, order.status)
    side_label = _ORDER_SIDE_LABEL.get(order.side, order.side)
    qty_str = _format_price(order.quantity)

    summary_parts = [f"{order.symbol} {side_label} {qty_str}"]
    if order.avg_fill_price is not None and order.status in ("filled", "partial"):
        summary_parts.append(f"@ {_format_price(order.avg_fill_price)}")
    summary_parts.append(f"· {status_label}")
    if order.status == "rejected" and order.error_message:
        summary_parts.append(f"· {order.error_message[:60]}")
    summary = " ".join(summary_parts)

    detail: dict[str, Any] = {
        "symbol": order.symbol,
        "side": order.side,
        "status": order.status,
        "order_type": order.order_type,
        "quantity": _format_price(order.quantity),
    }
    if order.filled_quantity is not None and order.filled_quantity > 0:
        detail["filled_quantity"] = _format_price(order.filled_quantity)
    if order.avg_fill_price is not None:
        detail["avg_fill_price"] = _format_price(order.avg_fill_price)
    if order.commission is not None and order.commission > 0:
        detail["commission"] = _format_price(order.commission)
    if order.pnl is not None:
        detail["pnl"] = _format_price(order.pnl)
    if order.exchange_order_id:
        detail["exchange_order_id"] = order.exchange_order_id
    if order.signal_id is not None:
        detail["signal_id"] = order.signal_id
    if order.error_message:
        detail["error_message"] = order.error_message

    # 时间：成交了用 filled_at；拒单/撤销用 cancelled_at；否则用 submitted_at / created_at
    if order.status in ("filled", "partial") and order.filled_at is not None:
        at = order.filled_at
    elif order.status == "cancelled" and order.cancelled_at is not None:
        at = order.cancelled_at
    elif order.submitted_at is not None:
        at = order.submitted_at
    else:
        at = order.created_at

    return {
        "id": f"order:{order.id}",
        "at": _isoformat(at),
        "type": "order",
        "severity": _order_severity(order),
        "instance_id": order.strategy_instance_id,
        "summary": summary[:200],
        "detail": detail,
    }


def _serialize_auto_pause(instance: StrategyInstance) -> dict[str, Any]:
    reason = instance.last_pause_reason or "auto:unknown"
    reason_label = _AUTO_PAUSE_REASON_LABEL.get(reason, reason)
    stopped_at = instance.last_stopped_at or instance.updated_at or instance.created_at
    return {
        "id": f"auto_pause:{instance.id}:{reason}",
        "at": _isoformat(stopped_at),
        "type": "auto_pause",
        "severity": "critical" if reason == "auto:state_drift" else "warning",
        "instance_id": instance.id,
        "summary": f'{instance.name or "策略"} 自动暂停 · {reason_label}'[:200],
        "detail": {
            "instance_name": instance.name,
            "reason": reason,
            "status": instance.status,
        },
    }


def _serialize_audit_event(event: AuditEvent) -> dict[str, Any]:
    return {
        "id": f"{event.type}:{event.id}",
        "at": _isoformat(event.created_at),
        "type": event.type,
        "severity": event.severity,
        "instance_id": event.instance_id,
        "account_id": event.account_id,
        "summary": event.summary,
        "detail": event.detail or {},
    }


def _signal_severity(signal: Signal) -> str:
    """信号默认 info，但 rejected 状态升级为 warning（下单失败值得关注）。"""
    if signal.status == "rejected":
        return "warning"
    return "info"


def _order_severity(order: Order) -> str:
    """订单 rejected/cancelled → warning；filled/submitted → info。"""
    if order.status in ("rejected", "cancelled"):
        return "warning"
    return "info"


def _matches_search(item: dict[str, Any], query: str | None) -> bool:
    if not query:
        return True
    haystacks = [str(item.get("summary", ""))]
    detail = item.get("detail")
    if isinstance(detail, dict):
        haystacks.extend(str(value) for value in detail.values() if value is not None)
    merged = " ".join(haystacks).lower()
    return query.lower() in merged


@router.get("")
async def list_events(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    event_type: EventType | None = Query(default=None),
    severity: Severity | None = Query(default=None),
    instance_id: int | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> APIResponse[dict[str, Any]]:
    """聚合事件流：signal/order/auto_pause（派生）+ risk_alert/user_action/system（audit_events）。"""
    signal_query = (
        select(Signal)
        .join(StrategyInstance, StrategyInstance.id == Signal.strategy_instance_id)
        .where(StrategyInstance.user_id == current_user.id)
    )
    if since is not None:
        signal_query = signal_query.where(Signal.created_at >= since)
    if until is not None:
        signal_query = signal_query.where(Signal.created_at <= until)
    if instance_id is not None:
        signal_query = signal_query.where(Signal.strategy_instance_id == instance_id)
    signal_query = signal_query.order_by(Signal.created_at.desc()).limit(500)
    signals = (await session.execute(signal_query)).scalars().all()

    # 订单事件 — 与策略实例关联（手工订单 strategy_instance_id is None 不出现在事件流）
    order_query = (
        select(Order)
        .join(ExchangeAccount, ExchangeAccount.id == Order.account_id)
        .where(ExchangeAccount.user_id == current_user.id)
        .where(Order.strategy_instance_id.is_not(None))
    )
    if since is not None:
        order_query = order_query.where(Order.created_at >= since)
    if until is not None:
        order_query = order_query.where(Order.created_at <= until)
    if instance_id is not None:
        order_query = order_query.where(Order.strategy_instance_id == instance_id)
    order_query = order_query.order_by(Order.created_at.desc()).limit(500)
    orders = (await session.execute(order_query)).scalars().all()

    # signal_id → Order 索引，让 _serialize_signal 能挂关联订单
    order_by_signal: dict[int, Order] = {o.signal_id: o for o in orders if o.signal_id is not None}

    pause_query = select(StrategyInstance).where(
        StrategyInstance.user_id == current_user.id,
        StrategyInstance.last_pause_reason.is_not(None),
    )
    if since is not None:
        pause_query = pause_query.where(StrategyInstance.last_stopped_at >= since)
    if until is not None:
        pause_query = pause_query.where(StrategyInstance.last_stopped_at <= until)
    if instance_id is not None:
        pause_query = pause_query.where(StrategyInstance.id == instance_id)
    pause_instances = (await session.execute(pause_query)).scalars().all()

    # 持久化审计事件：risk_alert / user_action / system 等
    # 注意：user_id 严格按 current_user 过滤，但 system 事件 user_id 是 NULL，
    # 单用户场景下也应当展示给当前用户 —— 用 or_(user_id == X, user_id is None)
    from sqlalchemy import or_

    audit_query = select(AuditEvent).where(
        or_(AuditEvent.user_id == current_user.id, AuditEvent.user_id.is_(None))
    )
    if since is not None:
        audit_query = audit_query.where(AuditEvent.created_at >= since)
    if until is not None:
        audit_query = audit_query.where(AuditEvent.created_at <= until)
    if instance_id is not None:
        audit_query = audit_query.where(AuditEvent.instance_id == instance_id)
    audit_query = audit_query.order_by(AuditEvent.created_at.desc()).limit(500)
    audit_events = (await session.execute(audit_query)).scalars().all()

    items: list[dict[str, Any]] = []
    items.extend(_serialize_signal(signal, order_by_signal.get(signal.id)) for signal in signals)
    items.extend(_serialize_order(order) for order in orders)
    items.extend(_serialize_auto_pause(instance) for instance in pause_instances)
    items.extend(_serialize_audit_event(event) for event in audit_events)

    if event_type is not None:
        items = [item for item in items if item["type"] == event_type]
    if severity is not None:
        items = [item for item in items if item.get("severity") == severity]
    if q:
        items = [item for item in items if _matches_search(item, q)]

    def _sort_key(item: dict[str, Any]) -> tuple[float, str]:
        raw = item.get("at") or ""
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return (dt.timestamp(), item["id"])
        except ValueError:
            return (0, item["id"])

    items.sort(key=_sort_key, reverse=True)
    total = len(items)
    page_items = items[offset : offset + limit]

    return APIResponse(
        data={
            "total": total,
            "items": page_items,
            "limit": limit,
            "offset": offset,
        }
    )
