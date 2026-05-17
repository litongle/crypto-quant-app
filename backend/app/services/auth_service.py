"""
认证服务 — 单用户版

只支持登录 + 刷新 token；admin 由 app.main.seed_admin() 启动时种子。
"""

import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_token,
)
from app.core.security import (
    verify_password as _verify_password,
)
from app.models.user import User
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)

# Redis key 前缀,值随便填,只看存在性。TTL 设到 token 原 exp + 5 分钟 buffer。
_REVOKED_REFRESH_PREFIX = "revoked_refresh:"


async def claim_refresh_jti(jti: str, exp_ts: int | None) -> bool:
    """原子化"check-and-mark":返回 True 表示当前调用拿到了使用权,False 表示已被吊销。

    用 Redis SET NX EX 一步完成:把"检查是否已用过"和"标记为已用"合并,
    避免 check→write 之间的 TOCTOU 窗口让并发的两枚同源请求都通过。

    Redis 故障 → 降级返回 True (放行)。revocation 是 defense in depth,
    Redis 抖动不应该让正常用户登录失败 (这是 24h 无人值守系统,可用性优先)。

    无 jti (老版部署前的 token) → 直接 True,兼容性放行一次。
    """
    if not jti:
        return True
    try:
        from app.config import get_settings
        from app.redis import get_redis_client

        if exp_ts:
            now_ts = int(datetime.now(UTC).timestamp())
            ttl = max(60, exp_ts - now_ts + 300)
        else:
            ttl = get_settings().refresh_token_expire_days * 24 * 3600

        r = await get_redis_client()
        # nx=True: 仅 key 不存在时设值,返回 True;已存在返回 None。
        result = await r.set(f"{_REVOKED_REFRESH_PREFIX}{jti}", "1", ex=ttl, nx=True)
        return bool(result)
    except Exception as exc:
        logger.warning("[refresh-rotation] Redis 失败,降级放行 jti=%s: %s", jti, exc)
        return True


class AuthService:
    """认证服务（单用户）"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.user_repo.get_by_email(email)
        if not user or not _verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="邮箱或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if user.status != "active":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账户已被禁用")
        return user

    async def login(self, email: str, password: str) -> tuple[User, str, str]:
        user = await self.authenticate(email, password)
        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})
        return user, access_token, refresh_token

    async def refresh_tokens(self, refresh_token: str) -> tuple[str, str]:
        try:
            payload = verify_token(refresh_token, token_type="refresh")
            user_id = payload.get("sub")
            jti = payload.get("jti")
            exp_ts = payload.get("exp")
            if user_id is None:
                raise HTTPException(status_code=401, detail="无效的刷新Token")
        except (JWTError, ValueError) as err:
            raise HTTPException(status_code=401, detail="无效的刷新Token") from err

        # 防 refresh 复用:check-and-mark 原子化(SETNX),并发同源请求只有一个能过。
        # claim 失败 = 已被旧 rotation 标记吊销 → 401。
        if not await claim_refresh_jti(jti, exp_ts):
            raise HTTPException(
                status_code=401,
                detail="刷新 Token 已被使用,请重新登录",
            )

        user = await self.user_repo.get_by_id(int(user_id))
        if not user or user.status != "active":
            raise HTTPException(status_code=401, detail="用户不存在或已禁用")

        access_token = create_access_token(data={"sub": str(user.id)})
        new_refresh_token = create_refresh_token(data={"sub": str(user.id)})
        return access_token, new_refresh_token
