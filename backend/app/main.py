"""
FastAPI 主入口

改动：
- 不再模块级缓存 settings，每次从 get_settings() 取
- 根路径 / 和 /web/ 增加 setup 跳转
- 注册安装向导 API
- P1-3: 行情 API 限流中间件
- P2-9: 改进全局异常处理器
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text

from app.config import get_settings
from app.core.exceptions import AppException

# ── 日志配置 ──────────────────────────────────────────────────────────
# Python 默认 root logger = WARNING 会把策略 tick / 启动 / 信号判断这些 INFO
# 日志全吞掉，导致"策略不动"这类问题在生产里完全 debug 不了。这里在模块
# 加载时显式拉到 INFO，并把过吵的第三方库压回 WARNING。可通过环境变量
# LOG_LEVEL=DEBUG/INFO/WARNING 覆盖。
_log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level_name, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
for _noisy in ("httpx", "httpcore", "urllib3", "sqlalchemy.engine", "websockets"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


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
            "（运行 `docker compose run --rm backend python -m scripts.generate_admin_hash` 生成）"
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    settings = get_settings()
    logger.info(
        "Starting %s v%s (env=%s)", settings.app_name, settings.app_version, settings.environment
    )

    # SQLite 试用模式 — 业务表数据量小够用,但写并发/崩溃恢复弱,不要拿来跑真盘
    if settings.database_url.startswith("sqlite"):
        logger.warning(
            "⚠️  SQLite 模式 — 仅适合试用/演示。跑真盘请设 "
            "DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname"
        )

    # 数据库 schema
    try:
        from app.database import init_db

        await init_db()
        logger.info("数据库表结构已就绪")
    except Exception as exc:
        logger.warning("数据库初始化失败: %s", exc)

    # 种子 admin（必须在 init_db 之后）
    try:
        await seed_admin()
    except Exception as exc:
        logger.warning("admin 种子失败: %s", exc)

    # 把 .env 中的运行时配置灌入 runtime_config 表（已存在的 key 不覆盖）
    try:
        from app.database import get_session_maker
        from app.services.runtime_config_service import bootstrap_runtime_config_from_env

        session_maker = await get_session_maker()
        async with session_maker() as session:
            await bootstrap_runtime_config_from_env(session)
    except Exception as exc:
        logger.warning("runtime_config bootstrap 失败: %s", exc)

    # 启动 WebSocket 行情代理
    try:
        from app.api.v1.ws_market import init_ws_proxies

        await init_ws_proxies()
    except Exception as exc:
        logger.warning("WebSocket 代理初始化失败（不影响 REST API）: %s", exc)

    # 自动 seed 策略模板
    try:
        from app.seed_data import init_strategy_templates

        await init_strategy_templates()
        logger.info("策略模板数据已就绪")
    except Exception as exc:
        logger.warning("策略模板初始化失败: %s", exc)

    # 启动策略运行器
    try:
        from app.core.strategy_runner import strategy_runner
        from app.database import get_session_maker

        session_maker = await get_session_maker()
        await strategy_runner.start(session_maker)
    except Exception as exc:
        logger.warning("策略运行器初始化失败: %s", exc)

    # 启动订单对账服务 — P0-3
    try:
        from app.services.order_reconciliation_service import start_reconciliation

        session_maker = await get_session_maker()
        await start_reconciliation(session_maker)
    except Exception as exc:
        logger.warning("订单对账服务初始化失败: %s", exc)

    # 启动定时同步调度器 — P1-4
    try:
        from app.services.sync_scheduler import start_sync_scheduler

        session_maker = await get_session_maker()
        await start_sync_scheduler(session_maker)
    except Exception as exc:
        logger.warning("定时同步调度器初始化失败: %s", exc)

    # 系统启动审计
    try:
        from app.database import get_session_maker
        from app.services.audit_service import log_system

        session_maker = await get_session_maker()
        await log_system(
            session_maker,
            event="app_started",
            summary=f"系统启动 · {settings.app_name} v{settings.app_version}",
            detail={"environment": settings.environment, "version": settings.app_version},
        )
    except Exception as exc:
        logger.warning("系统启动审计写入失败: %s", exc)

    yield

    # 系统停止审计（在依赖关闭前写，避免 session_maker 已 reset）
    try:
        from app.database import get_session_maker
        from app.services.audit_service import log_system

        session_maker = await get_session_maker()
        await log_system(
            session_maker,
            event="app_stopping",
            summary=f"系统关闭 · {settings.app_name}",
        )
    except Exception as exc:
        logger.warning("系统停止审计写入失败: %s", exc)

    # 关闭时清理
    try:
        from app.api.v1.ws_market import cleanup_ws_proxies

        await cleanup_ws_proxies()
    except Exception:
        pass
    try:
        from app.core.strategy_runner import strategy_runner

        await strategy_runner.stop()
    except Exception:
        pass
    try:
        from app.services.order_reconciliation_service import stop_reconciliation

        await stop_reconciliation()
    except Exception:
        pass
    try:
        from app.services.sync_scheduler import stop_sync_scheduler

        await stop_sync_scheduler()
    except Exception:
        pass
    try:
        from app.services.notification_service import notification_service

        await notification_service.close()
    except Exception:
        pass
    from app.redis import close_redis

    await close_redis()
    from app.database import reset_database

    await reset_database()
    logger.info("Shutting down...")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    settings = get_settings()

    # 生产/staging 关闭交互式文档 — 暴露完整 schema 等于给攻击者发地图,
    # 单用户系统没人需要在线 swagger UI,本机 dev 仍保留方便调试。
    _docs_enabled = not settings.is_production
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Alpha-7 量化交易后端 API",
        lifespan=lifespan,
        docs_url="/docs" if _docs_enabled else None,
        redoc_url="/redoc" if _docs_enabled else None,
        openapi_url="/openapi.json" if _docs_enabled else None,
    )

    # CORS - SEC-08: 限制方法和头部，不再使用通配符
    # Authorization header 已去掉:浏览器侧改走 HttpOnly cookie 不需要这头,
    # 留着只会扩大跨源 preflight 接受面;curl/脚本是同源场景,不走 CORS。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    # P0-3: 修复行情 API 限流内存泄漏 - 使用 Redis 实现
    # 改为使用 Redis 存储，支持多进程/多实例且有过期时间
    market_rate_limit = 60  # 每分钟请求上限
    market_rate_window = 60  # 窗口大小（秒）

    # 登录限流 — bcrypt verify 是 CPU 密集 (~100ms),不限流单 IP 一秒 10 次就把
    # 后端 CPU 打满。从 settings 取,测试环境可放宽避免连续 login 测试踩雷。
    login_rate_limit = settings.login_rate_limit_per_minute
    login_rate_window = 60

    # 注意中间件顺序:Starlette 后添加的中间件最先执行(outermost wrapper)。
    # security_headers 必须在 rate_limit 之后定义,这样 rate_limit 直接返回的
    # 429 响应也会经过 security_headers 加头(否则 429 裸吐没安全头)。

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        """API 限流 — 行情(防被薅) + 登录(防 bcrypt DoS)。"""
        path = request.url.path
        is_market = path.startswith("/api/v1/market") or path.startswith("/api/v1/ws/")
        is_login = path == "/api/v1/auth/login"
        if not (is_market or is_login):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        bucket = "login" if is_login else "market"
        limit = login_rate_limit if is_login else market_rate_limit
        window = login_rate_window if is_login else market_rate_window

        try:
            from app.redis import get_redis_client

            r = await get_redis_client()

            key = f"rate_limit:{bucket}:{client_ip}"

            # 使用 Redis INCR + EXPIRE 实现固定窗口限流
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, window)

            if count > limit:
                return JSONResponse(
                    status_code=429,
                    content={
                        "success": False,
                        "error": {
                            "code": "RATE_LIMITED",
                            "message": "请求频率超限，请稍后重试",
                        },
                    },
                )
        except Exception as exc:
            # Redis 故障时降级：记录日志并放行，避免影响核心业务
            logger.warning("[RateLimit] Redis 访问失败，已降级放行: %s", exc)

        return await call_next(request)

    # 安全响应头 — 基础加固 + CSP。
    # 定义在 rate_limit 之后 = 中间件外层 → 429 等早返回响应也会经过这里加头。
    _is_prod = settings.is_production

    # CSP — 务实版:前端有 116 处 inline handler + 217 处 inline style + 2 段 inline script,
    # 一次性收编是大重构;先卡死能挡的:
    #   - script-src 白名单: self + jsdelivr(图表/QR 库) + unsafe-inline(暂留 inline handler),
    #     这样 XSS 注 <script src="evil.com"> 会被挡 — 这是 XSS 最常见的提权路径
    #   - style-src: self + Google Fonts CSS + unsafe-inline(暂留 inline style)
    #   - font-src: Google Fonts CDN
    #   - img-src: self + data:(CSS 里大量 data:image/svg+xml 图标)
    #   - connect-src 'self': fetch/XHR 锁同源,前端目前不连任何 WS/外部 API
    #   - frame-ancestors 'none': 现代版 X-Frame-Options,挡点击劫持
    #   - form-action 'self': 防 XSS 注钓鱼 <form action="phish.com">
    #   - base-uri 'self': 防 <base href="evil"> 篡改所有相对路径
    #   - object-src 'none': 禁 <embed>/<object> plugin
    # TODO: 收完 inline handler 后可去 unsafe-inline,这样真能挡 XSS 注 <script>alert(1)</script>。
    _csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "worker-src 'self'; "
        "manifest-src 'self'; "
        "media-src 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "base-uri 'self'; "
        "object-src 'none'"
    )

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        # 防点击劫持:别人嵌 iframe 诱导用户"暂停策略/确认下单" (旧浏览器兼容,新版优先 CSP frame-ancestors)
        response.headers.setdefault("X-Frame-Options", "DENY")
        # 防 MIME 嗅探,避免 JS/HTML 被错误执行
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        # 跨域跳转不带完整 URL 出去(query 里可能有敏感参数)
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # 关掉 FLoC/topics 等浏览器 ad-tracking API,顺带消除 unload 警告相关项
        response.headers.setdefault("Permissions-Policy", "interest-cohort=(), browsing-topics=()")
        # CSP — 挡远程脚本/钓鱼表单/base 篡改/plugin 等 XSS 提权路径
        response.headers.setdefault("Content-Security-Policy", _csp)
        # HSTS 仅生产:本机 http://localhost 部署强制 HTTPS 会让浏览器拒连
        if _is_prod:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response

    # 异常处理
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        # 按异常类型映射到合适的 HTTP 状态码 — 之前一律 400 导致 token 过期被前端
        # 当成"参数错误"无法触发自动刷新,polling 死循环刷屏。
        from app.core.exceptions import (
            AlreadyExistsError,
            AuthenticationError,
            ExchangeAPIError,
            InsufficientBalanceError,
            NotFoundError,
            RateLimitError,
            RiskLimitExceededError,
            ValidationError,
        )

        if isinstance(exc, AuthenticationError):
            status_code = 401  # 前端 api.js 凭此触发 refresh token
        elif isinstance(exc, NotFoundError):
            status_code = 404
        elif isinstance(exc, AlreadyExistsError):
            status_code = 409
        elif isinstance(exc, RateLimitError):
            status_code = 429
        elif isinstance(exc, RiskLimitExceededError):
            status_code = 422
        elif isinstance(exc, ExchangeAPIError):
            status_code = 502
        elif isinstance(exc, (ValidationError, InsufficientBalanceError)):
            status_code = 400
        else:
            status_code = 400  # 兜底
        return JSONResponse(
            status_code=status_code,
            content={
                "success": False,
                "error": exc.to_dict(),
            },
        )

    # 全局异常处理 — P2-9: 区分 502/500，便于前端决定是否重试
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # 判断是否为网络/外部服务类错误（可重试）
        error_name = type(exc).__name__
        is_retryable = any(
            kw in error_name.lower() for kw in ("network", "timeout", "connection", "gateway")
        )
        # 判断是否为交易所相关异常
        is_exchange_error = "exchange" in error_name.lower() or "api" in error_name.lower()

        status_code = 502 if (is_retryable or is_exchange_error) else 500
        error_code = "EXTERNAL_SERVICE_ERROR" if status_code == 502 else "INTERNAL_ERROR"

        logger.error(
            "[GlobalExceptionHandler] %s: %s (path=%s, retryable=%s)",
            error_name,
            str(exc)[:200],
            request.url.path,
            is_retryable,
        )

        return JSONResponse(
            status_code=status_code,
            content={
                "success": False,
                "error": {
                    "code": error_code,
                    "message": (
                        "外部服务异常，请稍后重试" if status_code == 502 else "服务器内部错误"
                    ),
                    "retryable": is_retryable,
                },
            },
        )

    # P3-3: 健康检查详细信息
    @app.get("/health")
    async def health_check():
        checks = {"api": True, "version": get_settings().app_version}

        # 数据库连接检查
        try:
            from app.database import get_engine

            engine = await get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = True
        except Exception as exc:
            checks["database"] = False
            checks["database_error"] = str(exc)[:100]

        # Redis 连接检查
        try:
            from app.redis import get_redis_client

            r = await get_redis_client()
            if r:
                await r.ping()
                checks["redis"] = True
            else:
                checks["redis"] = False
                checks["redis_error"] = "client not initialized"
        except Exception as exc:
            checks["redis"] = False
            checks["redis_error"] = str(exc)[:100]

        is_healthy = checks.get("database", False)
        return JSONResponse(
            status_code=200 if is_healthy else 503,
            content={"status": "healthy" if is_healthy else "degraded", **checks},
        )

    # 根路径
    @app.get("/")
    async def root():
        return RedirectResponse(url="/web/")

    # 注册路由
    from app.api.v1 import api_router

    app.include_router(api_router, prefix="/api/v1")

    # Web 控制台
    from app.web.routes import router as web_router

    app.include_router(web_router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
