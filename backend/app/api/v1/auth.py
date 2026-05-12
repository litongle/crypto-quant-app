"""
认证 API — 单用户版

保留：/login, /refresh, /me。
删除：/register, /login-2fa, /2fa/setup, /2fa/verify, /2fa/disable, /2fa/status。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.schemas import APIResponse
from app.database import get_session
from app.models.user import User
from app.services.auth_service import AuthService

router = APIRouter()


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    risk_level: str
    status: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(TokenResponse):
    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


@router.post("/login")
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """单用户登录（生产环境必须 HTTPS）。"""
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
    return APIResponse(
        data=LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse.model_validate(user),
        ).model_dump()
    )


@router.post("/refresh")
async def refresh_token(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    auth_service = AuthService(session)
    access_token, new_refresh = await auth_service.refresh_tokens(request.refresh_token)
    return APIResponse(
        data=TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh,
        ).model_dump()
    )


@router.get("/me")
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
) -> APIResponse:
    return APIResponse(data=UserResponse.model_validate(current_user).model_dump())
