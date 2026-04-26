"""
RSI分层极值追踪自动量化交易系统 - 主入口文件

该文件是FastAPI应用的主入口点，包含：
- FastAPI应用初始化
- 中间件配置(CORS、安全、日志等)
- 路由注册
- 错误处理
- 应用启动和关闭事件
- 静态文件服务
- WebSocket支持
- 健康检查端点
"""

import os
import time
import logging
import asyncio
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Any, Optional, Union
from datetime import datetime, timedelta

import uvicorn
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, HTTPException, Depends, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.database import init_db, setup_timescale_hypertables, engine
from app.api.api_v1.api import api_router
from app.api.websocket.router import websocket_router
from app.tasks.worker import init_celery
from app.utils.error_handling import (
    init_error_handling, 
    get_logger, 
    get_trace_id, 
    set_trace_id, 
    clear_trace_id,
    AppError, 
    ErrorCode,
    send_alert
)


# 配置结构化日志
logger = get_logger("app.main")


# 自定义中间件
class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """请求日志中间件，记录所有HTTP请求"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # 获取客户端IP
        client_ip = request.client.host if request.client else "unknown"
        
        # 设置跟踪ID
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
        set_trace_id(trace_id)
        
        # 记录请求开始
        logger.debug(
            "开始处理请求", 
            extra={
                "method": request.method,
                "path": request.url.path,
                "client_ip": client_ip,
                "user_agent": request.headers.get("user-agent", "unknown")
            }
        )
        
        # 处理请求
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # 记录请求完成
            logger.debug(
                "请求完成", 
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "process_time": round(process_time, 4),
                    "client_ip": client_ip
                }
            )
            
            # 添加处理时间和跟踪ID到响应头
            response.headers["X-Process-Time"] = str(process_time)
            response.headers["X-Trace-ID"] = get_trace_id()
            
            return response
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                "请求异常", 
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e),
                    "process_time": round(process_time, 4),
                    "client_ip": client_ip
                },
                exc_info=True
            )
            raise
        finally:
            # 清理跟踪ID
            clear_trace_id()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件，限制每个IP的请求频率"""
    
    def __init__(self, app, rate_limit_per_minute: int = 100):
        super().__init__(app)
        self.rate_limit = rate_limit_per_minute
        self.ip_requests = {}  # IP -> [(timestamp, count), ...]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 获取客户端IP
        client_ip = request.client.host if request.client else "unknown"
        
        # 检查IP白名单
        if client_ip in settings.ip_whitelist_list:
            return await call_next(request)
        
        # 获取当前时间
        now = time.time()
        minute_ago = now - 60
        
        # 清理旧记录
        if client_ip in self.ip_requests:
            self.ip_requests[client_ip] = [
                (ts, count) for ts, count in self.ip_requests[client_ip] if ts > minute_ago
            ]
        
        # 计算最近一分钟的请求数
        recent_requests = sum(count for ts, count in self.ip_requests.get(client_ip, []))
        
        # 如果超过限制，返回429错误
        if recent_requests >= self.rate_limit:
            logger.warning(
                "速率限制触发", 
                extra={
                    "client_ip": client_ip,
                    "requests_count": recent_requests,
                    "rate_limit": self.rate_limit
                }
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "请求过于频繁，请稍后再试"}
            )
        
        # 更新请求计数
        if client_ip in self.ip_requests:
            if self.ip_requests[client_ip] and self.ip_requests[client_ip][-1][0] == int(now):
                # 如果最后一条记录是当前秒，增加计数
                ts, count = self.ip_requests[client_ip][-1]
                self.ip_requests[client_ip][-1] = (ts, count + 1)
            else:
                # 否则添加新记录
                self.ip_requests[client_ip].append((int(now), 1))
        else:
            self.ip_requests[client_ip] = [(int(now), 1)]
        
        # 处理请求
        return await call_next(request)


# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    description="RSI分层极值追踪自动量化交易系统API",
    version="0.1.0",
    docs_url="/api/docs" if settings.DEBUG_MODE else None,  # 仅在调试模式下启用Swagger UI
    redoc_url="/api/redoc" if settings.DEBUG_MODE else None,  # 仅在调试模式下启用ReDoc
    openapi_url="/api/openapi.json" if settings.DEBUG_MODE else None,  # 仅在调试模式下启用OpenAPI
)


# 配置中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)  # 启用Gzip压缩
app.add_middleware(SessionMiddleware, secret_key=settings.JWT_SECRET)  # 会话中间件
app.add_middleware(RequestLoggerMiddleware)  # 请求日志中间件
app.add_middleware(RateLimitMiddleware, rate_limit_per_minute=settings.RATE_LIMIT)  # 速率限制中间件

# 仅在生产环境中启用受信任主机中间件
if not settings.DEBUG_MODE:
    app.add_middleware(
        TrustedHostMiddleware, 
        allowed_hosts=settings.allowed_hosts_list
    )


# 注册路由
app.include_router(api_router, prefix=settings.API_PREFIX)


# 注册WebSocket路由
app.include_router(websocket_router)


# 配置静态文件
@app.on_event("startup")
async def setup_static_files():
    """配置静态文件服务"""
    try:
        static_dir = Path(settings.BASE_DIR) / "frontend" / "dist"
        if static_dir.exists():
            app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
            logger.info("静态文件已挂载", extra={"directory": str(static_dir)})
        else:
            logger.warning("静态文件目录不存在", extra={"directory": str(static_dir)})
    except Exception as e:
        logger.error("挂载静态文件失败", extra={"error": str(e)}, exc_info=True)


# 配置模板
templates = Jinja2Templates(directory="templates")


# 健康检查端点
@app.get("/api/v1/health", tags=["health"])
async def health_check():
    """健康检查端点"""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": app.version,
        "environment": "development" if settings.DEBUG_MODE else "production",
        "trace_id": get_trace_id()
    }


# 根路径重定向到前端
@app.get("/", include_in_schema=False)
async def root():
    """根路径重定向到前端"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="0;url=/index.html">
        <title>RSI分层极值追踪自动量化交易系统</title>
    </head>
    <body>
        <p>如果您没有被自动重定向，请<a href="/index.html">点击这里</a>。</p>
    </body>
    </html>
    """)


# 全局异常处理
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    """应用自定义异常处理器"""
    logger.warning(
        f"应用异常: {exc.code.name}",
        extra=exc.to_dict()
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=exc.to_dict()
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """HTTP异常处理器"""
    logger.warning(
        "HTTP异常", 
        extra={
            "status_code": exc.status_code,
            "detail": exc.detail,
            "path": request.url.path
        }
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "trace_id": get_trace_id()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """通用异常处理器"""
    trace_id = get_trace_id()
    logger.error(
        "未处理的异常", 
        extra={
            "error_type": type(exc).__name__,
            "error": str(exc),
            "path": request.url.path,
            "trace_id": trace_id
        },
        exc_info=True
    )
    
    # 对于严重异常，发送告警
    send_alert(
        level="ERROR",
        title="服务器未处理异常",
        message=f"路径: {request.url.path}\n错误: {str(exc)}",
        details={
            "error_type": type(exc).__name__,
            "path": str(request.url),
            "method": request.method,
            "trace_id": trace_id
        }
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "服务器内部错误",
            "trace_id": trace_id
        }
    )


# WebSocket连接管理
class WebSocketConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """添加新的WebSocket连接"""
        await websocket.accept()
        if client_id not in self.active_connections:
            self.active_connections[client_id] = []
        self.active_connections[client_id].append(websocket)
        logger.info("WebSocket连接已建立", extra={"client_id": client_id})
    
    def disconnect(self, websocket: WebSocket, client_id: str):
        """移除WebSocket连接"""
        if client_id in self.active_connections:
            if websocket in self.active_connections[client_id]:
                self.active_connections[client_id].remove(websocket)
            if not self.active_connections[client_id]:
                del self.active_connections[client_id]
        logger.info("WebSocket连接已关闭", extra={"client_id": client_id})
    
    async def broadcast(self, message: Dict[str, Any], client_id: Optional[str] = None):
        """广播消息"""
        if client_id:
            # 向特定客户端广播
            connections = self.active_connections.get(client_id, [])
            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(
                        "向客户端发送消息失败", 
                        extra={
                            "client_id": client_id,
                            "error": str(e)
                        },
                        exc_info=True
                    )
        else:
            # 向所有客户端广播
            for client_id, connections in self.active_connections.items():
                for connection in connections:
                    try:
                        await connection.send_json(message)
                    except Exception as e:
                        logger.error(
                            "向客户端发送消息失败", 
                            extra={
                                "client_id": client_id,
                                "error": str(e)
                            },
                            exc_info=True
                        )


# 创建WebSocket连接管理器
ws_manager = WebSocketConnectionManager()


# WebSocket端点
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket端点"""
    # 为WebSocket连接设置跟踪ID
    trace_id = str(uuid.uuid4())
    set_trace_id(trace_id)
    
    await ws_manager.connect(websocket, client_id)
    try:
        while True:
            # 接收消息
            data = await websocket.receive_json()
            logger.debug(
                "收到WebSocket消息", 
                extra={
                    "client_id": client_id,
                    "message_type": data.get("type"),
                    "trace_id": trace_id
                }
            )
            
            # 处理消息
            # 这里可以添加消息处理逻辑
            
            # 回复确认消息
            await websocket.send_json({
                "type": "ack",
                "timestamp": datetime.utcnow().isoformat(),
                "trace_id": trace_id,
                "data": {"received": True}
            })
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, client_id)
    except Exception as e:
        logger.error(
            "WebSocket错误", 
            extra={
                "client_id": client_id,
                "error": str(e),
                "trace_id": trace_id
            },
            exc_info=True
        )
        ws_manager.disconnect(websocket, client_id)
    finally:
        # 清理跟踪ID
        clear_trace_id()


# 应用启动事件
@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("应用启动中...")
    
    # 初始化错误处理系统
    try:
        init_error_handling()
        logger.info("错误处理系统初始化完成")
    except Exception as e:
        logger.error(
            "错误处理系统初始化失败", 
            extra={"error": str(e)}, 
            exc_info=True
        )
    
    # 初始化数据库
    try:
        init_db()
        logger.info("数据库初始化完成")
        
        # 设置TimescaleDB超表
        with engine.connect() as conn:
            setup_timescale_hypertables(conn)
            logger.info("TimescaleDB超表设置完成")
    except Exception as e:
        logger.error(
            "数据库初始化失败", 
            extra={"error": str(e)}, 
            exc_info=True
        )
        # 发送严重告警
        send_alert(
            level="CRITICAL",
            title="数据库初始化失败",
            message=f"应用启动时数据库初始化失败: {str(e)}",
            details={"error": str(e)}
        )
    
    # 初始化Celery
    try:
        init_celery()
        logger.info("Celery初始化完成")
    except Exception as e:
        logger.error(
            "Celery初始化失败", 
            extra={"error": str(e)}, 
            exc_info=True
        )
        # 发送告警
        send_alert(
            level="ERROR",
            title="Celery初始化失败",
            message=f"应用启动时Celery初始化失败: {str(e)}",
            details={"error": str(e)}
        )
    
    # 创建必要的目录
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    os.makedirs(settings.BACKUP_DIR, exist_ok=True)
    
    logger.info(
        f"{settings.APP_NAME} 已启动", 
        extra={
            "version": app.version,
            "environment": "development" if settings.DEBUG_MODE else "production"
        }
    )
    
    # 发送应用启动通知
    send_alert(
        level="INFO",
        title=f"{settings.APP_NAME} 已启动",
        message=f"版本: {app.version}\n环境: {'开发' if settings.DEBUG_MODE else '生产'}",
        details={
            "version": app.version,
            "environment": "development" if settings.DEBUG_MODE else "production",
            "host": settings.WEB_HOST,
            "port": settings.WEB_PORT
        }
    )


# 应用关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("应用关闭中...")
    
    # 关闭数据库连接
    try:
        engine.dispose()
        logger.info("数据库连接已关闭")
    except Exception as e:
        logger.error(
            "关闭数据库连接失败", 
            extra={"error": str(e)}, 
            exc_info=True
        )
    
    # 关闭WebSocket连接
    for client_id, connections in ws_manager.active_connections.items():
        for connection in connections:
            try:
                await connection.close()
            except Exception as e:
                logger.error(
                    "关闭WebSocket连接失败", 
                    extra={
                        "client_id": client_id,
                        "error": str(e)
                    },
                    exc_info=True
                )
    
    logger.info(f"{settings.APP_NAME} 已关闭")


# 仅在直接运行此文件时启动服务器
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.WEB_HOST,
        port=settings.WEB_PORT,
        reload=settings.DEBUG_MODE,
        workers=1,
        log_level=settings.LOG_LEVEL.lower(),
    )
