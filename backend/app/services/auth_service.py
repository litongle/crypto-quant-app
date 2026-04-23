"""
认证服务
"""
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token,
    pwd_context,
    verify_password as _verify_password,
    hash_password as _hash_password,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码（委托给 security 模块）"""
    return _verify_password(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """哈希密码（委托给 security 模块）"""
    return _hash_password(password)


class AuthService:
    """认证服务"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def register(
        self, email: str, password: str, name: str
    ) -> tuple[User, str, str]:
        """注册用户"""
        # 检查邮箱是否存在
        if await self.user_repo.email_exists(email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱已被注册",
            )

        # 创建用户
        hashed_password = get_password_hash(password)
        user = User(
            email=email,
            hashed_password=hashed_password,
            name=name,
        )
        user = await self.user_repo.create(user)

        # 生成Token
        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

        return user, access_token, refresh_token

    async def authenticate(self, email: str, password: str) -> User:
        """验证用户登录"""
        user = await self.user_repo.get_by_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="邮箱或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="邮箱或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账户已被禁用",
            )
        return user

    async def login(self, email: str, password: str) -> tuple[User, str, str]:
        """用户登录"""
        user = await self.authenticate(email, password)
        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})
        return user, access_token, refresh_token

    async def refresh_tokens(self, refresh_token: str) -> tuple[str, str]:
        """刷新Token"""
        try:
            # SEC-06: 必须验证 token 类型为 refresh
            payload = verify_token(refresh_token, token_type="refresh")
            user_id = payload.get("sub")
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="无效的刷新Token",
                )
        except (JWTError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的刷新Token",
            )

        # 验证用户存在
        user = await self.user_repo.get_by_id(int(user_id))
        if not user or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在或已禁用",
            )

        access_token = create_access_token(data={"sub": str(user.id)})
        new_refresh_token = create_refresh_token(data={"sub": str(user.id)})
        return access_token, new_refresh_token
