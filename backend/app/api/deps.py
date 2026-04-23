"""
FastAPI 依赖注入
"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import AuthenticationError, TokenExpiredError
from app.core.security import verify_token
from app.database import get_db
from app.models.user import User
from app.repositories.user_repo import UserRepository

security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """获取当前用户"""
    try:
        payload = verify_token(credentials.credentials, token_type="access")
        # SEC-07: sub 是 str 类型，需显式转换为 int
        sub = payload.get("sub")
        if sub is None:
            raise AuthenticationError()
        try:
            user_id = int(sub)
        except (ValueError, TypeError):
            raise AuthenticationError()
    except ValueError as e:
        if "expired" in str(e).lower():
            raise TokenExpiredError()
        raise AuthenticationError()

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise AuthenticationError()

    return user


# 类型别名，方便使用
CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
