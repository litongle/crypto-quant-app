"""
认证 API — 统一 APIResponse 响应格式
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field

from app.database import get_session
from app.models.user import User
from app.services.auth_service import AuthService
from app.api.deps import get_current_user
from app.core.schemas import APIResponse
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class RegisterRequest(BaseModel):
    """注册请求"""
    email: EmailStr
    password: str = Field(min_length=8, max_length=72, description="密码长度8-72位")
    name: str = Field(min_length=1, max_length=50)


class UserResponse(BaseModel):
    """用户响应"""
    id: int
    email: str
    name: str
    risk_level: str
    status: str

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshRequest(BaseModel):
    """刷新Token请求"""
    refresh_token: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """用户注册"""
    auth_service = AuthService(session)
    user, access_token, refresh_token = await auth_service.register(
        email=request.email,
        password=request.password,
        name=request.name,
    )
    return APIResponse(data=LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    ).model_dump())


@router.post("/login")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """用户登录"""
    auth_service = AuthService(session)
    user, access_token, refresh_token = await auth_service.login(
        email=form_data.username,
        password=form_data.password,
    )
    return APIResponse(data=LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    ).model_dump())


@router.post("/refresh")
async def refresh_token(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """刷新Token"""
    auth_service = AuthService(session)
    access_token, refresh_token = await auth_service.refresh_tokens(request.refresh_token)
    return APIResponse(data={
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    })


@router.get("/me")
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
) -> APIResponse:
    """获取当前用户信息"""
    return APIResponse(data=UserResponse.model_validate(current_user).model_dump())
