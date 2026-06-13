"""前端静态文件挂载。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.shared.utils.path_util import PROJECT_ROOT

FRONTEND_ROOT = PROJECT_ROOT / "app" / "resources" / "frontend"

def _html_file(filename: str) -> Path:
    path = FRONTEND_ROOT / filename
    if not path.exists():
        raise FileNotFoundError(f"前端页面不存在: {path}")
    return path


def html_response(filename: str) -> FileResponse:
    return FileResponse(_html_file(filename))


def admin_page_response() -> FileResponse:
    return html_response("admin.html")


def mount_frontend(app: FastAPI) -> None:
    """把当前项目里的原型前端挂到 FastAPI 服务上。"""
    static_dir = FRONTEND_ROOT / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def index_page():
        return admin_page_response()

    @app.get("/admin", include_in_schema=False)
    async def admin_page():
        return admin_page_response()

    @app.get("/login", include_in_schema=False)
    async def login_page():
        return html_response("login.html")

    @app.get("/demo", include_in_schema=False)
    async def demo_page():
        return html_response("demo.html")
