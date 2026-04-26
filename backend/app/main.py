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
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text

from app.config import get_settings
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    settings = get_settings()
    logger.info("Starting %s v%s (env=%s)", settings.app_name, settings.app_version, settings.environment)
    if settings.setup_required:
        logger.info("⚠️ 首次运行，请访问 /web/setup 完成安装向导")

    # 启动 WebSocket 行情代理
    try:
        from app.api.v1.ws_market import init_ws_proxies
        await init_ws_proxies()
    except Exception as exc:
        logger.warning("WebSocket 代理初始化失败（不影响 REST API）: %s", exc)

    # 自动 seed 策略模板（首次启动时）
    if not settings.setup_required:
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

    yield

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
    from app.redis import close_redis
    await close_redis()
    from app.database import reset_database
    await reset_database()
    logger.info("Shutting down...")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="币钱袋量化交易后端 API",
        lifespan=lifespan,
    )

    # CORS - SEC-08: 限制方法和头部，不再使用通配符
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )

    # P1-3: 行情 API 限流中间件（IP 级别，每分钟 60 次）
    _rate_limit_store: dict[str, list[float]] = defaultdict(list)
    MARKET_RATE_LIMIT = 60  # 每分钟请求上限
    MARKET_RATE_WINDOW = 60  # 窗口大小（秒）

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        """行情 API 限流"""
        # 仅对行情相关端点限流
        path = request.url.path
        if not (path.startswith("/api/v1/market") or path.startswith("/api/v1/ws/")):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # 清理过期记录
        timestamps = _rate_limit_store[client_ip]
        _rate_limit_store[client_ip] = [t for t in timestamps if now - t < MARKET_RATE_WINDOW]

        # 检查限流
        if len(_rate_limit_store[client_ip]) >= MARKET_RATE_LIMIT:
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

        _rate_limit_store[client_ip].append(now)
        return await call_next(request)

    # 异常处理
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=400,
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
            kw in error_name.lower()
            for kw in ("network", "timeout", "connection", "gateway")
        )
        # 判断是否为交易所相关异常
        is_exchange_error = "exchange" in error_name.lower() or "api" in error_name.lower()

        status_code = 502 if (is_retryable or is_exchange_error) else 500
        error_code = "EXTERNAL_SERVICE_ERROR" if status_code == 502 else "INTERNAL_ERROR"

        logger.error(
            "[GlobalExceptionHandler] %s: %s (path=%s, retryable=%s)",
            error_name, str(exc)[:200], request.url.path, is_retryable,
        )

        return JSONResponse(
            status_code=status_code,
            content={
                "success": False,
                "error": {
                    "code": error_code,
                    "message": "外部服务异常，请稍后重试" if status_code == 502 else "服务器内部错误",
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
            from app.services.market_service import get_redis_client
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

    # 根路径：根据安装状态跳转
    @app.get("/")
    async def root():
        if get_settings().setup_required:
            return RedirectResponse(url="/web/setup")
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
