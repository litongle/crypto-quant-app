"""事件流 API — 聚合交易信号与策略自停事件（单用户版，不再依赖审计日志）。"""

from datetime import UTC, datetime
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


def _isoformat(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat().replace("+00:00", "Z")


def _serialize_signal(signal: Signal) -> dict[str, Any]:
    action_map = {"buy": "买入", "sell": "卖出", "close": "平仓"}
    action_label = action_map.get(signal.action, signal.action)
    price = f" @ {signal.entry_price}" if signal.entry_price is not None else ""
    reason = f" · {signal.reason}" if signal.reason else ""
    return {
        "id": f"signal:{signal.id}",
        "at": _isoformat(signal.created_at),
        "type": "signal",
        "instance_id": signal.strategy_instance_id,
        "summary": f"{signal.symbol} {action_label}{price}{reason}"[:200],
        "detail": {
            "symbol": signal.symbol,
            "action": signal.action,
            "status": signal.status,
            "reason": signal.reason,
        },
    }


def _serialize_auto_pause(instance: StrategyInstance) -> dict[str, Any]:
    reason = instance.last_pause_reason or "auto:unknown"
    stopped_at = instance.last_stopped_at or instance.updated_at or instance.created_at
    return {
        "id": f"auto_pause:{instance.id}:{reason}",
        "at": _isoformat(stopped_at),
        "type": "auto_pause",
        "instance_id": instance.id,
        "summary": f'{instance.name or "策略"} 自动暂停 · {reason}'[:200],
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
