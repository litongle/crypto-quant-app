"""
认证 API — 单用户版

保留：/login, /refresh, /me, /logout。
删除：/register, /login-2fa, /2fa/setup, /2fa/verify, /2fa/disable, /2fa/status。

token 通过 HttpOnly + SameSite=Strict + (生产) Secure cookie 投递,
JS 无法直读,XSS 只能拿到空字符串。Bearer header 仍由 deps.py 兜底,
方便测试 / curl / 脚本访问。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.schemas import APIResponse
from app.core.security import verify_token
from app.database import get_session
from app.models.user import User
from app.services.auth_service import AuthService, _claim_refresh_jti

router = APIRouter()

# refresh_token cookie 收窄到 /api/v1/auth,只在 refresh/logout 时浏览器才会带出去,
# 其他业务接口拿不到 → 即便业务接口被 SSRF/重定向,refresh 也不会泄漏。
_AUTH_COOKIE_PATH = "/api/v1/auth"


def _set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
) -> None:
    """登录 / 刷新成功时统一下发两枚 HttpOnly cookie。"""
    settings = get_settings()
    secure = settings.is_production
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 3600,
        httponly=True,
        secure=secure,
        samesite="strict",
        path=_AUTH_COOKIE_PATH,
    )


def _clear_auth_cookies(response: Response) -> None:
    """登出时双 cookie 全清,path 必须与下发时一致才能命中。"""
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path=_AUTH_COOKIE_PATH)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    risk_level: str
    status: str


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """单用户登录（生产环境必须 HTTPS）。token 走 cookie,body 只回 user。"""
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").lower()
    if forwarded_proto not in ("", "https"):
        host = request.headers.get("host", "")
        if not any(dev in host for dev in ("localhost", "127.0.0.1", ":8000", ":5173")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="登录接口必须通过 HTTPS 传输，请确保反向代理已配置 SSL",
            )

    auth_service = AuthService(session)
    user, access_token, refresh_token = await auth_service.login(
        email=form_data.username,
        password=form_data.password,
    )
    _set_auth_cookies(response, access_token, refresh_token)
    return APIResponse(data=UserResponse.model_validate(user).model_dump())


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """从 refresh_token cookie 续期,无 cookie → 401"""
    token = request.cookies.get("refresh_token")
    if not token:
        raise AuthenticationError()
    auth_service = AuthService(session)
    access_token, new_refresh = await auth_service.refresh_tokens(token)
    _set_auth_cookies(response, access_token, new_refresh)
    return APIResponse(data={"ok": True})


@router.post("/logout")
async def logout(request: Request, response: Response) -> APIResponse:
    """清两枚 cookie + 把当前 refresh 的 jti 标记吊销。

    无鉴权依赖,避免 401 时无法 logout。
    revoke refresh:若攻击者通过 XSS / cookie 偷窃拿到了 refresh token 值,
    单清浏览器 cookie 没用,他还能 curl 重放。这里把 jti 也 mark 死,
    彻底封禁该 token (TTL 内不可再用)。
    """
    refresh = request.cookies.get("refresh_token")
    if refresh:
        try:
            payload = verify_token(refresh, token_type="refresh")
            jti = payload.get("jti")
            exp_ts = payload.get("exp")
            if jti:
                # 返回值不关心 — 不管是 newly 标记还是已被旧 rotation 标记,目标都达成
                await _claim_refresh_jti(jti, exp_ts)
        except Exception:
            # 即便 token 已过期 / 解码失败,仍要继续清 cookie
            pass
    _clear_auth_cookies(response)
    return APIResponse(data={"ok": True})


@router.get("/me")
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
) -> APIResponse:
    return APIResponse(data=UserResponse.model_validate(current_user).model_dump())
