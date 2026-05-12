# 单用户 + VPS 化部署改造实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将本项目从「多用户 + 安装向导 + 审计平台」形态收敛为「单用户 admin + VPS 部署 + 自用量化系统」形态，并补齐 VPS 反向代理部署文档。

**架构：**
- 认证：单一 admin 账户，用户名 + bcrypt 密码哈希存 `.env`，启动时种子到 `users` 表（user_id=1 固定），保留 JWT 登录 / refresh / me。
- 删除：安装向导（`/api/v1/setup` + `/web/setup`）、用户注册、TOTP/2FA、审计中间件 + 审计日志表、`/api/v1/users` 路由。
- 数据库：强制 PostgreSQL（沿用 docker-compose），删除 SQLite 默认 fallback。
- 部署：补 `docs/DEPLOY-VPS.md` + `deploy/Caddyfile.example`（Caddy 自动 HTTPS），README 替换安装向导引用。
- 一次性 Alembic 迁移 `0011` 清理 `audit_logs` 表 + `users.totp_*` + `users.is_superuser`。

**技术栈：** FastAPI + SQLAlchemy 2.x async + Alembic + bcrypt(passlib) + Postgres 16 + Redis 7 + Docker Compose + Caddy v2

---

## 设计依据（与 2026-05-09-frontend-restructure-design.md 协同）

前端形态已收敛（commit `6ef090d`），但后端仍保留 SaaS 残留：
- `api/v1/setup.py`（229 行）+ `web/static/setup.html`（511 行）—— 安装向导
- `api/v1/auth.py` 中 register / 2FA 系列端点（共 7 个）+ `services/totp_service.py`（93 行）
- `services/audit_service.py` + `api/audit_middleware.py` + `models/audit.py` + `api/v1/users.py` —— 审计体系（仅审计日志查询一个端点）
- `models/user.py` 中 `totp_secret/totp_enabled/totp_verified/is_superuser` 字段

定位为「个人自用 + 给朋友源码自部署」后，这些都是负担。

### 关键决策（已在 brainstorming 阶段对齐）

| 决策点 | 选择 | 否决方案 |
|---|---|---|
| 认证 | 单用户 admin + 应用 JWT 登录 | 无登录靠反代 BasicAuth；保留 TOTP |
| 节奏 | 一个 PR 一次性砍完 | 分阶段 |
| 数据库 | 强制 PG，删 SQLite fallback | 保留 SQLite 兼容 |
| 反向代理 | Caddy v2（自动 HTTPS） | Nginx + certbot |
| 单用户存储 | 保留 `users` 表 + 启动种子 user_id=1 | 完全去掉 User 模型 |

保留 `users` 表的原因：`ExchangeAccount.user_id` 和 `StrategyInstance.user_id` 都是外键依赖 —— 全删要动整个数据模型。保留表 + 固定单条记录是最小破坏方案。

---

## 文件结构

### 删除（共 7 个文件）

```
backend/app/api/v1/setup.py                  229 行  安装向导路由
backend/app/api/v1/users.py                  48  行  审计日志查询端点
backend/app/api/audit_middleware.py          88  行  审计中间件
backend/app/services/audit_service.py        102 行  审计服务
backend/app/services/totp_service.py         93  行  TOTP 服务
backend/app/models/audit.py                  63  行  AuditLog 模型
backend/app/web/static/setup.html            511 行  安装向导前端
backend/app/web/static/js/security.js        334 行  2FA + 审计 UI（前端重构已迁入设置抽屉，本次随安全/审计一起删）
```

### 修改

```
backend/app/config.py                  +admin_username +admin_password_hash；删 setup_complete/setup_required；强制 PG database_url 默认
backend/app/main.py                    删 lifespan setup_required 分支；删根路径 setup 跳转；删 AuditMiddleware 注册；新增 seed_admin lifespan 步骤
backend/app/api/v1/__init__.py         删 setup/users 路由挂载
backend/app/api/v1/auth.py             删 /register、/login-2fa、/2fa/* 五端点；login 不再返回 requires_2fa
backend/app/services/auth_service.py   删 register、login_with_2fa；login 改单一返回元组
backend/app/api/deps.py                （保持现状，JWT 仍生效）
backend/app/models/user.py             删 totp_secret/totp_enabled/totp_verified/is_superuser/has_2fa
backend/app/web/routes.py              删 /web/setup 路由
backend/app/web/static/index.html      删注册表单（行 55–76）+ 2FA 登录块（行 78–95）
backend/app/web/static/js/api.js       删 register、2FA 相关方法
backend/.env.example                   删 SETUP_COMPLETE；新增 ADMIN_USERNAME + ADMIN_PASSWORD_HASH；CORS_ORIGINS 加 VPS 域名占位
backend/tests/conftest.py              test_user 夹具改为「沿用启动种子的 admin」
backend/tests/test_auth.py             删 test_register_*；保留 login/me 测试
backend/tests/test_startup.py          删 setup_complete 相关断言
README.md                              删安装向导段落；新增 VPS 部署链接
```

### 新增

```
backend/scripts/generate-admin-hash.py 命令行工具：交互生成 ADMIN_PASSWORD_HASH
backend/alembic/versions/0011_remove_totp_audit_and_superuser.py  迁移：drop audit_logs/totp_*/is_superuser
docs/DEPLOY-VPS.md                     VPS 部署图文指南（含 Caddy + 防火墙 + 域名）
deploy/Caddyfile.example               Caddy 反向代理示例（自动 HTTPS）
docs/superpowers/specs/2026-05-13-single-user-vps-migration-design.md  本次改造的设计快照（可选随 PR 提交）
```

---

## 验证基线（每个 task 完成后跑）

```bash
docker compose run --rm backend ruff check .
docker compose run --rm backend python -m black --check .
docker compose run --rm backend pytest -x
```

---

### 任务 1：新增 admin 配置项 + 密码哈希工具

**文件：**
- 修改：`backend/app/config.py`
- 修改：`backend/.env.example`
- 创建：`backend/scripts/generate-admin-hash.py`
- 测试：`backend/tests/test_config.py`

- [ ] **步骤 1：在 `backend/tests/test_config.py` 末尾追加配置字段测试**

```python
def test_settings_has_admin_fields(monkeypatch):
    """admin 凭证字段应从环境变量读取"""
    monkeypatch.setenv("ADMIN_USERNAME", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$abcd")
    from app.config import reload_settings

    s = reload_settings()
    assert s.admin_username == "admin@example.com"
    assert s.admin_password_hash == "$2b$12$abcd"


def test_settings_no_setup_complete():
    """setup_complete / setup_required 应被删除"""
    from app.config import Settings

    assert not hasattr(Settings(), "setup_complete")
    assert not hasattr(Settings(), "setup_required")
```

- [ ] **步骤 2：运行测试确认失败**

```bash
docker compose run --rm backend pytest tests/test_config.py::test_settings_has_admin_fields tests/test_config.py::test_settings_no_setup_complete -v
```

预期：FAIL（字段不存在 / setup_complete 仍存在）。

- [ ] **步骤 3：修改 `backend/app/config.py`**

在 `Settings` 类中：
- 删除 `setup_complete: bool = False`
- 删除 `setup_required` property（行 79–83）
- 删除 SQLite 默认值，改为 PG 容器内地址
- 新增 admin 字段

```python
# 删除（原行 36）：
#   setup_complete: bool = False
# 删除（原行 79–83）：
#   @property
#   def setup_required(self) -> bool:
#       return not self.setup_complete

# 修改（原行 44）：
database_url: str = "postgresql+asyncpg://postgres:dev-postgres-password@postgres:5432/crypto_quant"

# 新增（放在 environment 之后）：
admin_username: str = "admin@example.com"
admin_password_hash: str = ""  # bcrypt 哈希，空值表示尚未配置
```

- [ ] **步骤 4：修改 `backend/.env.example`**

```bash
# 币钱袋量化交易后端 - 环境配置示例
# 部署：复制为 .env，跑 scripts/generate-admin-hash.py 生成 ADMIN_PASSWORD_HASH

# 应用配置
APP_NAME="CryptoQuant"
APP_VERSION="1.0.0"
DEBUG=false
ENVIRONMENT=production

# 安全密钥（生产请用 `openssl rand -hex 32` 生成）
SECRET_KEY=
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256

# 管理员账户（唯一登录账户）
ADMIN_USERNAME=admin@example.com
# 用 python -m scripts.generate-admin-hash 生成
ADMIN_PASSWORD_HASH=

# 数据库 / Redis（docker-compose 内置）
DATABASE_URL=postgresql+asyncpg://postgres:dev-postgres-password@postgres:5432/crypto_quant
REDIS_URL=redis://:dev-redis-password@redis:6379/0

# Token 过期时间
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS（VPS 部署填入你的域名）
CORS_ORIGINS=http://localhost:8001,http://127.0.0.1:8001,https://your-domain.example.com

# 交易所 API 配置（可选，也可在 Web 设置抽屉填写）
BINANCE_API_KEY=
BINANCE_API_SECRET=
OKX_API_KEY=
OKX_API_SECRET=
OKX_PASSPHRASE=

# 自停 / 异常告警
AUTO_PAUSE_CONSECUTIVE_ERRORS=5
AUTO_PAUSE_CONSECUTIVE_ORDER_FAILURES=3
AUTO_PAUSE_HEARTBEAT_MULTIPLIER=5
AUTO_PAUSE_HEARTBEAT_MIN_SECONDS=300
AUTO_PAUSE_WATCHDOG_INTERVAL_SECONDS=30

# 通知（可选）
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
WECOM_WEBHOOK_URL=
```

- [ ] **步骤 5：创建 `backend/scripts/generate-admin-hash.py`**

```python
#!/usr/bin/env python3
"""
生成 ADMIN_PASSWORD_HASH。

用法：
    docker compose run --rm backend python -m scripts.generate-admin-hash

会交互提示两遍密码，输出 bcrypt 哈希。把它复制到 .env 的 ADMIN_PASSWORD_HASH。
"""

import getpass
import sys

from app.core.security import hash_password


def main() -> int:
    pw1 = getpass.getpass("管理员密码：")
    if len(pw1) < 8:
        print("错误：密码至少 8 位", file=sys.stderr)
        return 1
    pw2 = getpass.getpass("再次输入：")
    if pw1 != pw2:
        print("错误：两次输入不一致", file=sys.stderr)
        return 1
    print()
    print("把下面这行复制到 .env：")
    print(f"ADMIN_PASSWORD_HASH={hash_password(pw1)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **步骤 6：运行测试确认通过**

```bash
docker compose run --rm backend pytest tests/test_config.py -v
```

预期：PASS。

- [ ] **步骤 7：Commit**

```bash
git add backend/app/config.py backend/.env.example backend/scripts/generate-admin-hash.py backend/tests/test_config.py
git commit -m "feat(config): 新增 ADMIN_USERNAME/ADMIN_PASSWORD_HASH 配置项，强制 PG 默认连接"
```

---

### 任务 2：启动时种子单一 admin

**文件：**
- 修改：`backend/app/main.py`
- 测试：`backend/tests/test_admin_seeder.py`（新建）

- [ ] **步骤 1：新建测试 `backend/tests/test_admin_seeder.py`**

```python
"""启动时 admin 种子逻辑测试。"""

import pytest
from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.models.user import User


@pytest.mark.asyncio
async def test_seed_admin_creates_user_when_empty(db_session, monkeypatch):
    """users 表为空时，应从 .env 创建 admin。"""
    from app.main import seed_admin

    pwd_hash = hash_password("test-admin-pw")
    monkeypatch.setattr("app.config.get_settings", lambda: _settings("admin@example.com", pwd_hash))

    await seed_admin()

    result = await db_session.execute(select(User))
    users = result.scalars().all()
    assert len(users) == 1
    assert users[0].email == "admin@example.com"
    assert verify_password("test-admin-pw", users[0].hashed_password)


@pytest.mark.asyncio
async def test_seed_admin_updates_hash_when_env_changes(db_session, test_user, monkeypatch):
    """已有 admin 时，.env 改了密码哈希应同步更新（不新建用户）。"""
    from app.main import seed_admin

    new_hash = hash_password("new-pw-456")
    monkeypatch.setattr(
        "app.config.get_settings", lambda: _settings(test_user.email, new_hash)
    )

    await seed_admin()
    await db_session.refresh(test_user)

    result = await db_session.execute(select(User))
    users = result.scalars().all()
    assert len(users) == 1
    assert verify_password("new-pw-456", users[0].hashed_password)


def _settings(username: str, password_hash: str):
    class _S:
        admin_username = username
        admin_password_hash = password_hash
        environment = "test"

    return _S()
```

- [ ] **步骤 2：运行测试确认失败**

```bash
docker compose run --rm backend pytest tests/test_admin_seeder.py -v
```

预期：FAIL（`seed_admin` 不存在）。

- [ ] **步骤 3：在 `backend/app/main.py` 中实现 `seed_admin`**

在 `lifespan` 函数定义之前（约行 21 之前）添加：

```python
async def seed_admin() -> None:
    """启动时确保单一 admin 存在；幂等。

    - users 表为空 → 用 .env 中的 ADMIN_USERNAME + ADMIN_PASSWORD_HASH 创建。
    - 已存在 admin → 同步 email/hash（支持改 .env 后重启即生效）。
    - ADMIN_PASSWORD_HASH 为空 → 仅警告，不创建（避免裸奔）。
    """
    from sqlalchemy import select

    from app.config import get_settings
    from app.database import get_session_maker
    from app.models.user import User

    settings = get_settings()
    if not settings.admin_password_hash:
        logger.warning(
            "ADMIN_PASSWORD_HASH 未设置；请在 .env 配置后重启。"
            "（运行 `python -m scripts.generate-admin-hash` 生成）"
        )
        return

    session_maker = await get_session_maker()
    async with session_maker() as session:
        result = await session.execute(select(User).limit(2))
        users = result.scalars().all()
        if len(users) > 1:
            logger.warning("users 表有 %d 条记录，本系统设计为单用户；保留第一条。", len(users))

        if not users:
            admin = User(
                email=settings.admin_username,
                hashed_password=settings.admin_password_hash,
                name="admin",
                status="active",
            )
            session.add(admin)
            await session.commit()
            logger.info("已创建 admin: %s", settings.admin_username)
        else:
            admin = users[0]
            changed = False
            if admin.email != settings.admin_username:
                admin.email = settings.admin_username
                changed = True
            if admin.hashed_password != settings.admin_password_hash:
                admin.hashed_password = settings.admin_password_hash
                changed = True
            if changed:
                await session.commit()
                logger.info("已同步 admin 凭证: %s", settings.admin_username)
```

然后在 `lifespan` 中 `init_db()` 之后、`init_strategy_templates` 之前调用：

```python
# 旧逻辑：if not settings.setup_required: ... init_db()
# 替换为（删 setup_required 分支，无条件 init_db + seed_admin）：
try:
    from app.database import init_db
    await init_db()
    logger.info("数据库表结构已就绪")
except Exception as exc:
    logger.warning("数据库初始化失败: %s", exc)

try:
    await seed_admin()
except Exception as exc:
    logger.warning("admin 种子失败: %s", exc)
```

- [ ] **步骤 4：运行测试确认通过**

```bash
docker compose run --rm backend pytest tests/test_admin_seeder.py -v
```

预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add backend/app/main.py backend/tests/test_admin_seeder.py
git commit -m "feat(auth): 启动时从 .env 种子单一 admin，幂等同步邮箱与密码哈希"
```

---

### 任务 3：删除 auth_service 中的 register / login_with_2fa

**文件：**
- 修改：`backend/app/services/auth_service.py`

- [ ] **步骤 1：覆写 `backend/app/services/auth_service.py` 为单用户版本**

```python
"""
认证服务 — 单用户版

只支持登录 + 刷新 token；admin 由 main.seed_admin() 启动时种子。
"""

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

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


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
            if user_id is None:
                raise HTTPException(status_code=401, detail="无效的刷新Token")
        except (JWTError, ValueError) as err:
            raise HTTPException(status_code=401, detail="无效的刷新Token") from err

        user = await self.user_repo.get_by_id(int(user_id))
        if not user or user.status != "active":
            raise HTTPException(status_code=401, detail="用户不存在或已禁用")

        access_token = create_access_token(data={"sub": str(user.id)})
        new_refresh_token = create_refresh_token(data={"sub": str(user.id)})
        return access_token, new_refresh_token
```

- [ ] **步骤 2：跑现有认证测试验证 login/refresh 仍可用**

```bash
docker compose run --rm backend pytest tests/test_auth.py::test_login_success tests/test_auth.py::test_login_wrong_password tests/test_auth.py::test_get_me_authenticated -v
```

预期：3 条 PASS。`test_register_*` 暂时还会失败，下一任务处理。

- [ ] **步骤 3：Commit**

```bash
git add backend/app/services/auth_service.py
git commit -m "refactor(auth): 移除 register/login_with_2fa，AuthService 收敛为单用户登录与 token 刷新"
```

---

### 任务 4：改造 auth 路由：删 register + 所有 2FA 端点

**文件：**
- 修改：`backend/app/api/v1/auth.py`
- 修改：`backend/tests/test_auth.py`

- [ ] **步骤 1：覆写 `backend/app/api/v1/auth.py` 为单用户版本**

```python
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
```

- [ ] **步骤 2：修改 `backend/tests/test_auth.py`，删除 register 测试**

完整替换为：

```python
"""认证流程测试 — 单用户登录 / 刷新 / me。"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user):
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "test@example.com", "password": "testpass123"},
    )
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user):
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "test@example.com", "password": "wrongpassword"},
    )
    assert resp.status_code in (401, 400)


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_register_endpoint_removed(client: AsyncClient):
    """/auth/register 应已删除"""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "x@y.com", "password": "Password123", "name": "x"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_2fa_endpoints_removed(client: AsyncClient, auth_headers):
    """所有 /auth/2fa/* 应已删除"""
    for path in (
        "/api/v1/auth/2fa/setup",
        "/api/v1/auth/2fa/verify",
        "/api/v1/auth/2fa/disable",
        "/api/v1/auth/2fa/status",
        "/api/v1/auth/login-2fa",
    ):
        resp = await client.post(path, headers=auth_headers, json={"code": "123456"})
        assert resp.status_code == 404, f"{path} should be 404, got {resp.status_code}"
```

- [ ] **步骤 3：运行测试**

```bash
docker compose run --rm backend pytest tests/test_auth.py -v
```

预期：全部 PASS。

- [ ] **步骤 4：Commit**

```bash
git add backend/app/api/v1/auth.py backend/tests/test_auth.py
git commit -m "refactor(auth-api): 移除注册与 2FA 端点，保留单用户 login/refresh/me"
```

---

### 任务 5：删除 TOTP service + User 模型 TOTP/superuser 字段

**文件：**
- 删除：`backend/app/services/totp_service.py`
- 修改：`backend/app/models/user.py`

- [ ] **步骤 1：删除 `backend/app/services/totp_service.py`**

```bash
git rm backend/app/services/totp_service.py
```

- [ ] **步骤 2：覆写 `backend/app/models/user.py` 删除 TOTP/superuser 字段**

```python
"""
用户模型（单用户场景：实际只存在 user_id=1 的 admin）。
"""

from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    """用户模型"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        Enum("active", "inactive", "banned", name="user_status"),
        default="active",
    )
    risk_level: Mapped[str] = mapped_column(
        Enum("conservative", "moderate", "aggressive", name="risk_level"),
        default="moderate",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    accounts = relationship("ExchangeAccount", back_populates="user", lazy="selectin")
    strategies = relationship("StrategyInstance", back_populates="user", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
```

- [ ] **步骤 3：搜索并修复仍引用已删字段的代码**

```bash
docker compose run --rm backend grep -rn "totp_secret\|totp_enabled\|totp_verified\|has_2fa\|is_superuser" app/ tests/
```

预期所有命中点都在「即将被删除的文件」（audit/security.js 等）。如果有其他文件命中，需在本步修复。

- [ ] **步骤 4：跑认证 + 数据库回归**

```bash
docker compose run --rm backend pytest tests/test_auth.py tests/test_database.py tests/test_admin_seeder.py -v
```

预期：全部 PASS。

- [ ] **步骤 5：Commit**

```bash
git add backend/app/models/user.py backend/app/services/totp_service.py
git commit -m "refactor(user): 删除 TOTP/superuser 字段与 totp_service"
```

---

### 任务 6：删除审计体系 + users 路由

**文件：**
- 删除：`backend/app/api/audit_middleware.py`
- 删除：`backend/app/services/audit_service.py`
- 删除：`backend/app/models/audit.py`
- 删除：`backend/app/api/v1/users.py`
- 修改：`backend/app/main.py`
- 修改：`backend/app/api/v1/__init__.py`

- [ ] **步骤 1：删除 4 个文件**

```bash
git rm backend/app/api/audit_middleware.py \
       backend/app/services/audit_service.py \
       backend/app/models/audit.py \
       backend/app/api/v1/users.py
```

- [ ] **步骤 2：修改 `backend/app/main.py` 移除 AuditMiddleware 注册**

定位 `# 审计日志中间件 — P1-6` 注释块（约行 138–145），整段删除：

```python
# 删除：
#   try:
#       from app.api.audit_middleware import AuditMiddleware
#       app.add_middleware(AuditMiddleware)
#       logger.info("审计日志中间件已注册")
#   except Exception as exc:
#       logger.warning("审计日志中间件注册失败: %s", exc)
```

- [ ] **步骤 3：修改 `backend/app/api/v1/__init__.py`**

```python
"""API v1 Router"""

from fastapi import APIRouter

from app.api.v1 import asset, auth, backtest, events, market, orders, strategies, ws

api_router = APIRouter()

# 认证
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])

# 策略
api_router.include_router(strategies.router, prefix="/strategies", tags=["策略"])

# 回测
api_router.include_router(backtest.router, prefix="/backtest", tags=["回测"])

# 市场数据
api_router.include_router(market.router, prefix="/market", tags=["行情"])

# 资产
api_router.include_router(asset.router, prefix="/asset", tags=["资产"])

# 交易/订单
api_router.include_router(orders.router, prefix="/trading", tags=["交易"])

# 事件流
api_router.include_router(events.router, prefix="/events", tags=["事件"])

# WebSocket 行情推送
api_router.include_router(ws.router, prefix="/ws", tags=["WebSocket"])
```

- [ ] **步骤 4：搜索残留引用并修复**

```bash
docker compose run --rm backend grep -rn "audit_middleware\|AuditMiddleware\|audit_service\|AuditService\|models.audit\|audit_logs" app/ tests/
```

如有命中：删除或注释相应导入与调用。预期此时只在 Alembic 历史迁移文件中有命中（保留）。

- [ ] **步骤 5：跑回归**

```bash
docker compose run --rm backend pytest -x
```

预期：全部 PASS（如有依赖审计的旧测试，删除该测试文件，并在 commit 信息中注明）。

- [ ] **步骤 6：Commit**

```bash
git add -A backend/app/
git commit -m "refactor: 删除审计中间件、审计服务、审计日志模型与 /users 路由"
```

---

### 任务 7：删除安装向导

**文件：**
- 删除：`backend/app/api/v1/setup.py`
- 删除：`backend/app/web/static/setup.html`
- 修改：`backend/app/web/routes.py`
- 修改：`backend/app/api/v1/__init__.py`
- 修改：`backend/app/main.py`
- 修改：`backend/tests/test_startup.py`

- [ ] **步骤 1：删除两个文件**

```bash
git rm backend/app/api/v1/setup.py backend/app/web/static/setup.html
```

- [ ] **步骤 2：修改 `backend/app/web/routes.py`**

完整覆写：

```python
"""Web 控制台路由 — 单用户版"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

STATIC_DIR = (Path(__file__).parent / "static").resolve()


@router.get("/web")
@router.get("/web/")
async def web_index():
    """网页控制台入口"""
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/web/static/{path:path}")
async def web_static(path: str):
    try:
        candidate = (STATIC_DIR / path).resolve()
        candidate.relative_to(STATIC_DIR)
    except (ValueError, OSError):
        raise HTTPException(status_code=404, detail="Not found") from None

    if candidate.is_file():
        return FileResponse(candidate)
    raise HTTPException(status_code=404, detail="Not found")
```

- [ ] **步骤 3：修改 `backend/app/api/v1/__init__.py`，确认不再有 `from app.api.v1 import setup`**

（任务 6 已经清理，此处再验证一遍）

```bash
grep -n "setup" backend/app/api/v1/__init__.py
```

预期：无命中。

- [ ] **步骤 4：修改 `backend/app/main.py` 删除根路径 setup 跳转 + lifespan 中的 setup_required 块**

定位以下三处并修改：

1. `lifespan` 中（约行 30–35）：
```python
# 删除：
#   if settings.setup_required:
#       logger.info("⚠️ 首次运行，请访问 /web/setup 完成安装向导")
```

2. `lifespan` 中（约行 38–45 与 60–65）：移除所有 `if not settings.setup_required:` 守卫，直接执行内部块（任务 2 已处理 init_db；这里同步移除 init_strategy_templates 的守卫）。

3. 根路径（约行 250–253）：
```python
# 旧：
#   @app.get("/")
#   async def root():
#       if get_settings().setup_required:
#           return RedirectResponse(url="/web/setup")
#       return RedirectResponse(url="/web/")
# 新：
@app.get("/")
async def root():
    return RedirectResponse(url="/web/")
```

- [ ] **步骤 5：修改 `backend/tests/test_startup.py`，移除 `setup_complete` 设置**

```bash
docker compose run --rm backend grep -n "setup_complete\|setup_required" tests/test_startup.py
```

把所有 `settings.setup_complete = True` 行删掉。

- [ ] **步骤 6：新增向导路由 404 验证测试**

在 `backend/tests/test_auth.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_setup_endpoints_removed(client: AsyncClient):
    """/api/v1/setup/* 与 /web/setup 应已删除"""
    for path in ("/api/v1/setup/status", "/api/v1/setup/env-defaults", "/web/setup"):
        resp = await client.get(path)
        assert resp.status_code == 404, f"{path} should be 404, got {resp.status_code}"
```

- [ ] **步骤 7：跑回归**

```bash
docker compose run --rm backend pytest -x
```

预期：全部 PASS。

- [ ] **步骤 8：Commit**

```bash
git add -A backend/
git commit -m "refactor: 删除安装向导（API + setup.html + 根路径跳转）"
```

---

### 任务 8：前端 index.html / api.js 删除注册与 2FA UI

**文件：**
- 修改：`backend/app/web/static/index.html`
- 修改：`backend/app/web/static/js/api.js`
- 删除：`backend/app/web/static/js/security.js`

- [ ] **步骤 1：删除 `backend/app/web/static/js/security.js`**

```bash
git rm backend/app/web/static/js/security.js
```

- [ ] **步骤 2：修改 `backend/app/web/static/index.html`**

a) 定位注册表单（行 55–76 之间，以 `<div id="register-form"` 起），整块删除。

b) 定位 2FA 登录块（以 `<div id="login-2fa"` 或 "验证并登录" 起，行 78–95），整块删除。

c) 在登录表单（行 24 起）的「忘记密码 / 注册」链接区域，删除指向注册的链接（搜索 `showRegister` 调用并删除对应 `<span>`）。

d) 搜索 `security.js`、`loadSecurityPage`、`security-page`、`/2fa/`、`register-form` 等残留引用并删除/注释。

具体定位命令：

```bash
grep -n "register-form\|login-2fa\|showRegister\|cancelLogin2fa\|loadSecurityPage\|security.js\|/2fa/" backend/app/web/static/index.html
```

逐一处理每条命中。

- [ ] **步骤 3：修改 `backend/app/web/static/js/api.js` 删除 register 与 2FA 方法**

定位命中点：

```bash
grep -n "register\|/2fa/\|login-2fa\|loginWith2fa\|setup2FA\|verify2FA\|disable2FA" backend/app/web/static/js/api.js
```

删除：
- `register(email, password, name)` 方法
- `loginWith2fa(...)` 方法
- `setup2FA() / verify2FA() / disable2FA() / get2FAStatus()` 方法
- 任何对 `/api/v1/setup/*`、`/api/v1/users/*` 的调用

- [ ] **步骤 4：浏览器手动验证**

```bash
docker compose up -d --build
```

打开 `http://localhost:8001/`：
- 看到登录页（不再有注册链接、不再有 2FA 输入框）。
- 用 `.env` 中的 `ADMIN_USERNAME` + `generate-admin-hash.py` 生成时的明文密码登录。
- 登录后控制台正常加载，4 个侧栏（控制台 / 策略 / 回测 / 事件流）齐全。
- 浏览器 DevTools Console 无 404 / undefined 报错。

- [ ] **步骤 5：Commit**

```bash
git add -A backend/app/web/static/
git commit -m "feat(web): 删除注册表单、2FA 登录块与 security.js，前端收敛为单用户登录"
```

---

### 任务 9：Alembic 迁移 0011（drop totp/audit/superuser）

**文件：**
- 创建：`backend/alembic/versions/0011_remove_totp_audit_and_superuser.py`

- [ ] **步骤 1：创建迁移文件**

```python
"""drop audit_logs / users.totp_* / users.is_superuser

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-13 00:00:00.000000

单用户化改造（spec 2026-05-13-single-user-vps-migration-design）：
- 删除审计日志表
- 删除 users 表中 TOTP 字段（totp_secret/totp_enabled/totp_verified）
- 删除 users 表中 is_superuser 字段
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) drop audit_logs（含索引）
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    # 2) drop users.totp_*
    op.drop_column("users", "totp_verified")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")

    # 3) drop users.is_superuser
    op.drop_column("users", "is_superuser")


def downgrade() -> None:
    # 反向重建（与 0003 upgrade 对齐）
    op.add_column(
        "users",
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("totp_secret", sa.String(255), nullable=True))
    op.add_column(
        "users", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default="0")
    )
    op.add_column(
        "users", sa.Column("totp_verified", sa.Boolean(), nullable=False, server_default="0")
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
```

- [ ] **步骤 2：在已运行数据库上跑 upgrade，确认无错**

```bash
docker compose run --rm backend alembic upgrade head
```

预期输出包含 `Running upgrade 0010 -> 0011`。

- [ ] **步骤 3：跑 downgrade 验证可逆，再 upgrade 回最新**

```bash
docker compose run --rm backend alembic downgrade -1
docker compose run --rm backend alembic upgrade head
```

预期两条命令都成功。

- [ ] **步骤 4：Commit**

```bash
git add backend/alembic/versions/0011_remove_totp_audit_and_superuser.py
git commit -m "feat(db): 迁移 0011 — drop audit_logs/users.totp_*/users.is_superuser"
```

---

### 任务 10：VPS 部署文档 + Caddyfile

**文件：**
- 创建：`docs/DEPLOY-VPS.md`
- 创建：`deploy/Caddyfile.example`
- 修改：`README.md`

- [ ] **步骤 1：创建 `deploy/Caddyfile.example`**

```caddyfile
# 把 your-domain.example.com 改为你的真实域名。
# Caddy 自动申请并续期 Let's Encrypt 证书。
#
# 启动：
#   sudo apt install caddy
#   sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
#   sudo systemctl reload caddy

your-domain.example.com {
    # 反代到 docker-compose 暴露的 8001
    reverse_proxy 127.0.0.1:8001 {
        header_up X-Forwarded-Proto {scheme}
        header_up X-Real-IP {remote_host}
    }

    # 安全头
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
    }

    encode gzip zstd

    log {
        output file /var/log/caddy/crypto-quant.log
        format console
    }
}
```

- [ ] **步骤 2：创建 `docs/DEPLOY-VPS.md`**

```markdown
# VPS 部署指南（单用户量化系统）

> 适用：1 核 1G 以上的 Linux VPS（Ubuntu 22.04+ / Debian 12+）。预计 30 分钟完成。

## 前置准备

- 一台 VPS，且 SSH 可登录
- 一个域名，且 A 记录已指向 VPS IP
- 自己的交易所 API key（合约权限）

## 1. 装 Docker + Compose

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# 重新登录后生效
```

## 2. 克隆仓库

```bash
git clone https://github.com/litongle/crypto-quant-app.git
cd crypto-quant-app
```

## 3. 配置 `.env`

```bash
cp backend/.env.example backend/.env
# 生成 ADMIN_PASSWORD_HASH（交互输入密码）
docker compose run --rm backend python -m scripts.generate-admin-hash
# 把输出的 ADMIN_PASSWORD_HASH=... 填入 backend/.env
# 同时填：
#   ADMIN_USERNAME（你的登录邮箱）
#   SECRET_KEY / JWT_SECRET_KEY（用 `openssl rand -hex 32` 各生成一条）
#   CORS_ORIGINS（加上 https://你的域名）
```

## 4. 启动后端

```bash
docker compose up -d --build
docker compose logs -f backend
# 看到 "Started CryptoQuant" 即成功
```

此时 `127.0.0.1:8001` 已经在服务，但还没暴露公网。

## 5. 配置 Caddy 反向代理（自动 HTTPS）

```bash
sudo apt install -y caddy
sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo sed -i 's/your-domain.example.com/你的域名/' /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy 会自动签发 Let's Encrypt 证书。10 秒后访问 `https://你的域名` 应看到登录页。

## 6. 配置防火墙

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

**关键**：postgres（5432）和 redis（6379）由 docker-compose 绑定到 `127.0.0.1`，不会暴露公网；后端的 8001 同样不要直接暴露，全部走 Caddy。

## 7. 验证

- 浏览器打开 `https://你的域名`
- 用 `.env` 里的 `ADMIN_USERNAME` + 步骤 3 输入的明文密码登录
- 进设置抽屉，填交易所 API key
- 在策略页启动 RSI 分层策略，观察事件流

## 日常维护

```bash
# 看日志
docker compose logs -f backend

# 升级
git pull
docker compose up -d --build
docker compose run --rm backend alembic upgrade head

# 重启
docker compose restart backend

# 改 admin 密码：重新跑 generate-admin-hash，更新 .env，docker compose restart backend
```

## 备份

```bash
# Postgres 数据
docker compose exec postgres pg_dump -U postgres crypto_quant > backup_$(date +%F).sql

# 全套（含卷）
docker run --rm -v crypto-quant-app_postgres_data:/data -v $PWD:/backup alpine \
  tar czf /backup/pg_data_$(date +%F).tar.gz /data
```

## 给朋友自部署

把整个仓库源码 + 本文档发给他，他按上述 7 步走即可。每个人有独立 VPS、独立 admin、独立交易所 key —— 互不影响。
```

- [ ] **步骤 3：修改 `README.md`**

```bash
grep -n "安装向导\|setup\|/web/setup\|首次进入" README.md
```

对每条命中：
- 把「访问 `http://localhost:8000/` 自动进入安装向导」替换为「访问 `http://localhost:8001/`，用 `.env` 中的 ADMIN_USERNAME / 密码登录」。
- 在「快速启动」之后新增一行链接：「**VPS 生产部署：见 [docs/DEPLOY-VPS.md](docs/DEPLOY-VPS.md)**」。
- 移除 `setup.py` 的目录树注释行。

- [ ] **步骤 4：Commit**

```bash
git add deploy/Caddyfile.example docs/DEPLOY-VPS.md README.md
git commit -m "docs: 新增 VPS 部署指南（Caddy 自动 HTTPS）+ 替换 README 安装向导引用"
```

---

### 任务 11：spec 文档归档 + 全量回归

**文件：**
- 创建：`docs/superpowers/specs/2026-05-13-single-user-vps-migration-design.md`

- [ ] **步骤 1：归档设计文档**

把本 plan 的「设计依据」「关键决策」「文件结构」三章节抽出来，写入 `docs/superpowers/specs/2026-05-13-single-user-vps-migration-design.md`，与 `2026-05-09-frontend-restructure-design.md` 风格一致，便于事后翻查。

- [ ] **步骤 2：跑完整回归**

```bash
docker compose run --rm backend ruff check .
docker compose run --rm backend python -m black --check .
docker compose run --rm backend pytest
```

预期：三条命令全部 0 退出码。

- [ ] **步骤 3：docker compose 实测启动**

```bash
docker compose down
docker compose up -d --build
docker compose logs --tail 80 backend
```

逐项确认 logs 中包含：
- `数据库表结构已就绪`
- `已创建 admin: <ADMIN_USERNAME>`（首次）或 `已同步 admin 凭证`（重启）
- 不再有 `审计日志中间件已注册` 或 `首次运行，请访问 /web/setup`

- [ ] **步骤 4：浏览器端到端**

打开 `http://localhost:8001/`：
1. 直达登录页（无 setup 跳转）。
2. 没有注册按钮、没有 2FA 输入框。
3. 用 admin 登录成功。
4. 4 个侧栏（控制台 / 策略 / 回测 / 事件流）齐全；设置抽屉内含交易所 / 风控 tab。
5. DevTools Console 无 4xx / 报错。

- [ ] **步骤 5：Commit + 推分支**

```bash
git add docs/superpowers/specs/2026-05-13-single-user-vps-migration-design.md
git commit -m "docs(specs): 归档 2026-05-13 单用户 + VPS 化改造设计快照"
```

---

## 自检清单（执行前最后看一遍）

- [ ] **规格覆盖度**：删 setup ✅ 任务 7；删 register/2FA ✅ 任务 3+4+8；删 audit ✅ 任务 6；改单用户 ✅ 任务 1+2；VPS 文档 ✅ 任务 10；DB 迁移 ✅ 任务 9。
- [ ] **占位符扫描**：所有任务步骤都给出具体代码、命令、预期；无 "TODO / 后续 / 类似上文" 字样。
- [ ] **类型一致性**：`seed_admin` 在任务 2 定义，任务 11 logs 中引用 `已创建 admin` 字符串一致；`LoginResponse` 在任务 4 重新定义后不再含 `requires_2fa`，与任务 3 的 `login()` 返回三元组一致。
- [ ] **顺序依赖**：任务 1（配置字段）→ 任务 2（种子）→ 任务 3-4（服务/路由删 2FA）→ 任务 5（模型删字段）→ 任务 6（删审计）→ 任务 7（删向导）→ 任务 8（前端）→ 任务 9（迁移 DB）→ 任务 10-11（文档+收尾）。任意一步失败可在该任务回滚单步，不影响下游。

---

## 风险与回滚

| 风险 | 缓解 |
|---|---|
| `.env` 没填 `ADMIN_PASSWORD_HASH` 直接重启 | `seed_admin` 已加 warning + 不创建用户，登录会失败但系统不崩溃 |
| 已存在用户的库（不止 admin 一个）迁移后丢失访问 | 任务 2 中 `seed_admin` 仅同步第一条；其余用户保留但需手动清理 |
| Alembic 0011 在生产 PG 上失败 | 任务 9 步骤 3 已验证 downgrade 可逆；线上前在 dump 上预演 |
| Caddy 配置错误导致 HTTPS 失败 | 任务 10 文档明确「先验证 http 内网联通，再上 Caddy」 |

---

## 执行交接

**计划已完成并保存到 `docs/superpowers/plans/2026-05-13-single-user-vps-migration.md`。两种执行方式：**

**1. 子代理驱动（推荐）** — 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** — 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

**选哪种方式？**
