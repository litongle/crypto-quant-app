"""
FastAPI 主入口

改动：
- 不再模块级缓存 settings，每次从 get_settings() 取
- 根路径 / 和 /web/ 增加 setup 跳转
- 注册安装向导 API
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

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

    # 全局异常处理
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务器内部错误",
                },
            },
        )

    # 健康检查
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": get_settings().app_version}

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
