"""
审计日志中间件 - P1-6

自动记录所有写操作（POST/PUT/PATCH/DELETE）到审计日志。
排除健康检查等无需审计的端点。
"""

import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

# 无需审计的路径前缀
_AUDIT_SKIP_PREFIXES = (
    "/health",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/login-2fa",
    "/api/v1/auth/refresh",
    "/api/v1/auth/2fa/",
    "/api/v1/ws/",
)

# 可审计的 HTTP 方法
_AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class AuditMiddleware(BaseHTTPMiddleware):
    """审计日志中间件"""

    async def dispatch(self, request: Request, call_next) -> Response:
        # 只审计写操作
        if request.method not in _AUDIT_METHODS:
            return await call_next(request)

        # 跳过无需审计的路径
        path = request.url.path
        if any(path.startswith(p) for p in _AUDIT_SKIP_PREFIXES):
            return await call_next(request)

        # 执行请求
        response = await call_next(request)

        # 尝试记录审计日志（异步，不阻塞响应）
        try:
            from app.database import get_session_maker

            user_id = getattr(request.state, "user_id", None)
            if user_id is None:
                # 尝试从 token 中提取
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    try:
                        from app.core.security import decode_token

                        payload = decode_token(auth_header[7:])
                        user_id = int(payload.get("sub", 0))
                    except Exception:
                        pass

            if user_id:
                action = (
                    f"{request.method.lower()}_{path.replace('/api/v1/', '').replace('/', '_')}"
                )
                status = "success" if 200 <= response.status_code < 400 else "failure"

                session_maker = await get_session_maker()
                async with session_maker() as session:
                    audit = AuditService(session)
                    await audit.log(
                        user_id=user_id,
                        action=action,
                        resource=path.split("/")[3] if len(path.split("/")) > 3 else "",
                        detail=f"{request.method} {path}",
                        ip_address=request.client.host if request.client else None,
                        user_agent=request.headers.get("User-Agent"),
                        status=status,
                    )
                    await session.commit()
        except Exception as exc:
            logger.debug("[AuditMiddleware] 审计记录失败: %s", exc)

        return response
