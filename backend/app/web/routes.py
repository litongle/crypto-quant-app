"""
Web 控制台路由 - 轻量网页前端 + 安装向导

路由：
- /web/setup  → 安装向导页面（首次运行）
- /web/       → 主控制台（安装完成后）
- /web/static → 静态文件
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from app.config import get_settings

router = APIRouter()

STATIC_DIR = (Path(__file__).parent / "static").resolve()


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
    """静态文件（缺失时返回 404，禁止用 index.html 冒充 JS/CSS，否则整站脚本崩溃）"""
    try:
        candidate = (STATIC_DIR / path).resolve()
        candidate.relative_to(STATIC_DIR)
    except (ValueError, OSError):
        raise HTTPException(status_code=404, detail="Not found") from None

    if candidate.is_file():
        return FileResponse(candidate)
    raise HTTPException(status_code=404, detail="Not found")
