"""用户查询端 FastAPI 应用。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handlers import install_error_handlers
from app.api.query.routers import chat, widget
from app.infra.config.providers import infra_config
from app.infra.persistence.bootstrap import init_database


def create_query_app() -> FastAPI:
    app = FastAPI(title=infra_config.app.query_app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(infra_config.app.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_error_handlers(app)

    app.include_router(widget.router)
    app.include_router(chat.router)

    @app.on_event("startup")
    async def startup() -> None:
        init_database(seed=True)

    return app


app = create_query_app()
