"""
FastAPI 依赖注入
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, TokenExpiredError
from app.core.security import verify_token
from app.database import get_db
from app.models.user import User
from app.repositories.user_repo import UserRepository

# auto_error=False:没带 token 时不要让 fastapi 返回 403 "Not authenticated"
# (语义错的 — 应该是 401 "请登录"),改由下面显式 raise AuthenticationError
# → 异常处理器映射到 401,前端 api.js 拦截器才会触发 refresh / 跳登录。
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """获取当前用户"""
    if credentials is None:
        raise AuthenticationError()
    try:
        payload = verify_token(credentials.credentials, token_type="access")
        # SEC-07: sub 是 str 类型，需显式转换为 int
        sub = payload.get("sub")
        if sub is None:
            raise AuthenticationError()
        try:
            user_id = int(sub)
        except (ValueError, TypeError) as err:
            raise AuthenticationError() from err
    except ValueError as err:
        if "expired" in str(err).lower():
            raise TokenExpiredError() from err
        raise AuthenticationError() from err

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise AuthenticationError()

    return user


# 类型别名，方便使用
CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
