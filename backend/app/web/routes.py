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
