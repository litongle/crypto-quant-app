"""
Web 控制台路由 - 轻量网页前端 + 安装向导

路由：
- /web/setup  → 安装向导页面（首次运行）
- /web/       → 主控制台（安装完成后）
- /web/static → 静态文件
"""
from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path

from app.config import get_settings

router = APIRouter()

STATIC_DIR = Path(__file__).parent / "static"


@router.get("/web")
@router.get("/web/")
async def web_index():
    """网页控制台入口"""
    if get_settings().setup_required:
        return RedirectResponse("/web/setup")
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/web/setup")
async def web_setup():
    """安装向导页面"""
    if not get_settings().setup_required:
        return RedirectResponse("/web/")
    return FileResponse(STATIC_DIR / "setup.html")


@router.get("/web/static/{path:path}")
async def web_static(path: str):
    """静态文件"""
    file_path = STATIC_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(STATIC_DIR / "index.html")
