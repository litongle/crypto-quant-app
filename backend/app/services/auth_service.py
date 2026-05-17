"""
认证服务 — 单用户版

只支持登录 + 刷新 token；admin 由 app.main.seed_admin() 启动时种子。
"""

import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer
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

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Redis key 前缀,值随便填,只看存在性。TTL 设到 token 原 exp + 5 分钟 buffer。
_REVOKED_REFRESH_PREFIX = "revoked_refresh:"


async def _is_refresh_jti_revoked(jti: str) -> bool:
    """检查 refresh token 的 jti 是否已被 rotation 标记吊销。

    Redis 故障 → 降级返回 False (放行)。revocation 是 defense in depth,
    Redis 抖动不应该让正常用户登录失败 (这是 24h 无人值守系统,优先可用性)。
    """
    try:
        from app.redis import get_redis_client

        r = await get_redis_client()
        return bool(await r.exists(f"{_REVOKED_REFRESH_PREFIX}{jti}"))
    except Exception as exc:
        logger.warning("[refresh-rotation] Redis 检查失败,降级放行 jti=%s: %s", jti, exc)
        return False


async def _mark_refresh_jti_revoked(jti: str, exp_ts: int | None) -> None:
    """把已用过的 refresh jti 写入 revocation set,过期前不可复用。

    TTL = token 剩余有效期 + 5 分钟 buffer。无 exp 时按 7 天兜底。
    """
    if not jti:
        return
    try:
        from app.config import get_settings
        from app.redis import get_redis_client

        if exp_ts:
            now_ts = int(datetime.now(UTC).timestamp())
            ttl = max(60, exp_ts - now_ts + 300)
        else:
            ttl = get_settings().refresh_token_expire_days * 24 * 3600

        r = await get_redis_client()
        await r.set(f"{_REVOKED_REFRESH_PREFIX}{jti}", "1", ex=ttl)
    except Exception as exc:
        logger.warning("[refresh-rotation] Redis 写入失败,跳过 jti=%s: %s", jti, exc)


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

        # 防 refresh 复用:每枚 refresh token 只能用一次,旧 jti 立即吊销。
        # 老版无 jti 的 token(部署前签发)放行一次,使用后再签发的会带 jti。
        if jti and await _is_refresh_jti_revoked(jti):
            raise HTTPException(
                status_code=401,
                detail="刷新 Token 已被使用,请重新登录",
            )

        user = await self.user_repo.get_by_id(int(user_id))
        if not user or user.status != "active":
            raise HTTPException(status_code=401, detail="用户不存在或已禁用")

        # 标记当前 jti 已使用,然后签发新对。顺序很重要:先 mark 再 issue,
        # 避免新 token 签出后用户立刻拿旧 token 再来一次 → 双花。
        await _mark_refresh_jti_revoked(jti, exp_ts)
        access_token = create_access_token(data={"sub": str(user.id)})
        new_refresh_token = create_refresh_token(data={"sub": str(user.id)})
        return access_token, new_refresh_token
