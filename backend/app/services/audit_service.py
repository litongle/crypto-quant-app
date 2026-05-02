"""
审计日志服务 - P1-6

提供审计日志写入和查询能力。
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """审计日志服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        user_id: int,
        action: str,
        resource: str | None = None,
        resource_id: int | None = None,
        detail: str | None = None,
        old_value: dict | None = None,
        new_value: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        status: str = "success",
        error_message: str | None = None,
    ) -> AuditLog:
        """记录审计日志"""
        log_entry = AuditLog(
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            detail=detail,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            error_message=error_message,
        )
        self.session.add(log_entry)
        await self.session.flush()
        return log_entry

    async def query(
        self,
        user_id: int | None = None,
        action: str | None = None,
        resource: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        """查询审计日志"""
        query = select(AuditLog)

        if user_id is not None:
            query = query.where(AuditLog.user_id == user_id)
        if action:
            query = query.where(AuditLog.action == action)
        if resource:
            query = query.where(AuditLog.resource == resource)
        if start_time:
            query = query.where(AuditLog.created_at >= start_time)
        if end_time:
            query = query.where(AuditLog.created_at <= end_time)
        if status:
            query = query.where(AuditLog.status == status)

        query = query.order_by(desc(AuditLog.created_at)).offset(offset).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        """序列化值以便 JSON 存储"""
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat() + "Z"
        return value

    def _make_safe_dict(self, data: dict) -> dict:
        """将字典值转为 JSON 安全格式"""
        if not data:
            return data
        return {k: self._serialize_value(v) for k, v in data.items()}
