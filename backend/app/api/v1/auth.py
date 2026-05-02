"""
认证 API — 统一 APIResponse 响应格式
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.schemas import APIResponse
from app.database import get_session
from app.models.user import User
from app.services.auth_service import AuthService

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


class TokenResponse(BaseModel):
    """Token响应"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(TokenResponse):
    """登录响应"""

    user: UserResponse
    requires_2fa: bool = False


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
    await session.commit()
    return APIResponse(
        data=LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse.model_validate(user),
        ).model_dump()
    )


@router.post("/login")
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """用户登录（生产环境必须 HTTPS）"""
    # HTTPS 强制检查：反向代理必须传 X-Forwarded-Proto
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").lower()
    if forwarded_proto not in ("", "https"):
        # 本地开发环境（无反向代理）跳过检查
        host = request.headers.get("host", "")
        if not any(dev in host for dev in ("localhost", "127.0.0.1", ":8000", ":5173")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="登录接口必须通过 HTTPS 传输，请确保反向代理已配置 SSL",
            )

    auth_service = AuthService(session)
    user, access_token, refresh_token, requires_2fa = await auth_service.login(
        email=form_data.username,
        password=form_data.password,
    )
    return APIResponse(
        data=LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse.model_validate(user),
            requires_2fa=requires_2fa,
        ).model_dump()
    )


@router.post("/refresh")
async def refresh_token(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """刷新Token (P2-18: 统一响应格式)"""
    auth_service = AuthService(session)
    access_token, refresh_token = await auth_service.refresh_tokens(request.refresh_token)
    return APIResponse(
        data=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        ).model_dump()
    )


@router.get("/me")
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
) -> APIResponse:
    """获取当前用户信息"""
    return APIResponse(data=UserResponse.model_validate(current_user).model_dump())


# ============ TOTP 2FA API — P1-5 ============


class TotpSetupResponse(BaseModel):
    """TOTP 设置响应"""

    secret: str
    uri: str


class TotpVerifyRequest(BaseModel):
    """TOTP 验证请求"""

    code: str = Field(min_length=6, max_length=6, description="6位数字验证码")


class TotpLoginRequest(BaseModel):
    """2FA 登录请求"""

    email: EmailStr
    password: str
    code: str = Field(min_length=6, max_length=6, description="6位TOTP验证码")


@router.post("/2fa/setup")
async def setup_2fa(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse[TotpSetupResponse]:
    """生成 TOTP 密钥和二维码 URI"""
    from app.services.totp_service import encrypt_totp_secret, generate_totp_secret

    result = await generate_totp_secret(current_user.id, current_user.email)

    # 加密存储 secret（暂未启用，等用户 verify 后才设置 totp_verified）
    encrypted = encrypt_totp_secret(result["secret"])
    current_user.totp_secret = encrypted
    current_user.totp_enabled = True
    current_user.totp_verified = False
    await session.commit()

    return APIResponse(
        data=TotpSetupResponse(
            secret=result["secret"],
            uri=result["uri"],
        ).model_dump()
    )


@router.post("/2fa/verify")
async def verify_2fa(
    request: TotpVerifyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """验证并启用 2FA"""
    from app.services.totp_service import decrypt_totp_secret, verify_totp

    if not current_user.totp_secret or not current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="请先发起 2FA 设置")
    if current_user.totp_verified:
        raise HTTPException(status_code=400, detail="2FA 已启用")

    secret = decrypt_totp_secret(current_user.totp_secret)
    if not await verify_totp(secret, request.code):
        raise HTTPException(status_code=400, detail="验证码无效")

    current_user.totp_verified = True
    await session.commit()

    return APIResponse(message="2FA 已启用")


@router.post("/2fa/disable")
async def disable_2fa(
    request: TotpVerifyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """禁用 2FA（需验证当前 TOTP）"""
    from app.services.totp_service import decrypt_totp_secret, verify_totp

    if not current_user.totp_secret or not current_user.has_2fa:
        raise HTTPException(status_code=400, detail="2FA 未启用")

    secret = decrypt_totp_secret(current_user.totp_secret)
    if not await verify_totp(secret, request.code):
        raise HTTPException(status_code=400, detail="验证码无效")

    current_user.totp_secret = None
    current_user.totp_enabled = False
    current_user.totp_verified = False
    await session.commit()

    return APIResponse(message="2FA 已禁用")


@router.post("/2fa/status")
async def get_2fa_status(
    current_user: Annotated[User, Depends(get_current_user)],
) -> APIResponse:
    """获取 2FA 状态"""
    return APIResponse(
        data={
            "enabled": current_user.totp_enabled,
            "verified": current_user.totp_verified,
            "has_2fa": current_user.has_2fa,
        }
    )


@router.post("/login-2fa")
async def login_with_2fa(
    request: TotpLoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> APIResponse:
    """带 2FA 验证的登录"""
    auth_service = AuthService(session)
    user, access_token, refresh_token = await auth_service.login_with_2fa(
        email=request.email,
        password=request.password,
        totp_code=request.code,
    )
    return APIResponse(
        data=LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse.model_validate(user),
        ).model_dump()
    )
