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
from app.models.order import Signal
from app.models.strategy import StrategyInstance
from app.models.user import User

router = APIRouter()

EventType = Literal["signal", "auto_pause"]

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


def _serialize_signal(signal: Signal) -> dict[str, Any]:
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
    return {
        "id": f"signal:{signal.id}",
        "at": _isoformat(signal.created_at),
        "type": "signal",
        "instance_id": signal.strategy_instance_id,
        "summary": summary[:200],
        "detail": {
            "symbol": signal.symbol,
            "action": signal.action,
            "status": signal.status,
            "reason": signal.reason,
        },
    }


def _serialize_auto_pause(instance: StrategyInstance) -> dict[str, Any]:
    reason = instance.last_pause_reason or "auto:unknown"
    reason_label = _AUTO_PAUSE_REASON_LABEL.get(reason, reason)
    stopped_at = instance.last_stopped_at or instance.updated_at or instance.created_at
    return {
        "id": f"auto_pause:{instance.id}:{reason}",
        "at": _isoformat(stopped_at),
        "type": "auto_pause",
        "instance_id": instance.id,
        "summary": f'{instance.name or "策略"} 自动暂停 · {reason_label}'[:200],
        "detail": {
            "instance_name": instance.name,
            "reason": reason,
            "status": instance.status,
        },
    }


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
    instance_id: int | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> APIResponse[dict[str, Any]]:
    """聚合交易信号和策略自停事件。"""
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

    items: list[dict[str, Any]] = []
    items.extend(_serialize_signal(signal) for signal in signals)
    items.extend(_serialize_auto_pause(instance) for instance in pause_instances)

    if event_type is not None:
        items = [item for item in items if item["type"] == event_type]
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
