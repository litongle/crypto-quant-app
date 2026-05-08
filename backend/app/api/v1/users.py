"""
用户 API — 审计日志查询
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.schemas import APIResponse
from app.database import get_session
from app.services.audit_service import AuditService

router = APIRouter()


@router.get("/audit-logs")
async def get_audit_logs(
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    action: str = Query(None, description="操作类型筛选"),
    resource: str = Query(None, description="资源类型筛选"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> APIResponse:
    """查询当前用户的审计日志"""
    service = AuditService(session)
    logs = await service.query(
        user_id=current_user.id,
        action=action,
        resource=resource,
        limit=limit,
        offset=offset,
    )
    return APIResponse(
        data=[
            {
                "id": log.id,
                "action": log.action,
                "resource": log.resource,
                "resourceId": log.resource_id,
                "detail": log.detail,
                "status": log.status,
                "ipAddress": log.ip_address,
                "createdAt": log.created_at.isoformat() + "Z" if log.created_at else "",
            }
            for log in logs
        ]
    )
