"""Web 控制台路由 — 单用户版"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

router = APIRouter()

STATIC_DIR = (Path(__file__).parent / "static").resolve()

# /web/static/*.{js,css,woff2,svg,png...} 永远配 ?v=<bump> querystring 做 cache-busting,
# 改文件就 bump,所以可以放心永久 immutable。
# index.html 与 sw.js 必须每次都拉新版,否则 ?v= 也没用。
_STATIC_IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
_NO_CACHE = "no-cache, no-store, must-revalidate"

# SPA history routing：前端用 history.pushState，刷新 /web/<page> 时后端要返回 index.html
# 由前端 _VALID_PAGES 校验非法 slug
_SPA_PAGES = {"dashboard", "strategy", "backtest", "events"}

# 复数形态等常见手误 → 301 到规范单数路径。paper/accounts 没有独立 SPA 页（走设置抽屉），
# 重定向到 dashboard 比直接 404 友好。
_PAGE_ALIASES = {
    "strategies": "strategy",
    "backtests": "backtest",
    "event": "events",
    "log": "events",
    "logs": "events",
    "paper": "dashboard",
    "papers": "dashboard",
    "account": "dashboard",
    "accounts": "dashboard",
}

_NOT_FOUND_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>页面不存在 · Alpha-7</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root{color-scheme:dark light}
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       background:#0b0d12;color:#e6e8eb;font-family:-apple-system,'Segoe UI',sans-serif}
  .wrap{text-align:center;padding:32px;max-width:480px}
  h1{font-size:64px;margin:0;color:#6366F1}
  p{color:#94a3b8;line-height:1.6;margin:8px 0 24px}
  a{display:inline-block;padding:10px 20px;background:#6366F1;color:#fff;
    border-radius:6px;text-decoration:none;font-weight:600}
  a:hover{background:#4f46e5}
</style></head>
<body><div class="wrap">
  <h1>404</h1>
  <p>页面 <code>__PATH__</code> 不存在。请从控制台进入。</p>
  <a href="/web/dashboard">回到控制台</a>
</div></body></html>"""


def _render_not_found(path: str) -> HTMLResponse:
    """str.format() 会被 CSS 里的 `{}` 误食，改用 replace；同时对 path 做 HTML 转义防注入"""
    safe_path = (
        path.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
    body = _NOT_FOUND_HTML.replace("__PATH__", safe_path)
    return HTMLResponse(body, status_code=404)


@router.get("/web")
@router.get("/web/")
async def web_index():
    """网页控制台入口"""
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": _NO_CACHE},
    )


@router.get("/favicon.ico")
async def favicon():
    """避免浏览器每次打页面都打一次 404；用 SVG icon 即可，无需单独 ico 文件"""
    return Response(status_code=204)


@router.get("/web/static/sw.js")
async def web_sw():
    """Service Worker —— 单独路由以附 Service-Worker-Allowed header

    sw.js 物理位于 /web/static/ 下，但需要控制 /web/ 主页面。
    浏览器只在响应带 Service-Worker-Allowed 时才允许 scope 高于 sw.js 路径。
    定义在通配静态路由前确保精确匹配先生效。
    """
    return FileResponse(
        STATIC_DIR / "sw.js",
        headers={
            "Service-Worker-Allowed": "/web/",
            # sw.js 也要永远拉新版,否则 CACHE_NAME bump 进不到浏览器
            "Cache-Control": _NO_CACHE,
        },
    )


@router.get("/web/static/{path:path}")
async def web_static(path: str):
    try:
        candidate = (STATIC_DIR / path).resolve()
        candidate.relative_to(STATIC_DIR)
    except (ValueError, OSError):
        return _render_not_found(f"/web/static/{path}")

    if candidate.is_file():
        return FileResponse(
            candidate,
            headers={"Cache-Control": _STATIC_IMMUTABLE_CACHE},
        )
    return _render_not_found(f"/web/static/{path}")


@router.get("/web/{page}")
async def web_spa_page(page: str):
    """SPA deep link：刷新 /web/dashboard 等路径时返回 index.html，由前端路由解析

    复数/常见手误走 301 别名；其他非法路径返回友好 HTML 404，不再裸吐 JSON detail。
    """
    if page in _SPA_PAGES:
        return FileResponse(
            STATIC_DIR / "index.html",
            headers={"Cache-Control": _NO_CACHE},
        )
    alias = _PAGE_ALIASES.get(page)
    if alias:
        return RedirectResponse(url=f"/web/{alias}", status_code=301)
    return _render_not_found(f"/web/{page}")
