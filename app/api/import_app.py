"""管理端 / 导入端 FastAPI 应用。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handlers import install_error_handlers
from app.api.frontend import mount_frontend
from app.api.import_.routers import (
    auth,
    business_line,
    chat_session,
    company,
    dashboard,
    document,
    knowledge_base,
    model_config,
    playground,
)
from app.api.query.routers import chat as query_chat
from app.api.query.routers import widget as query_widget
from app.infra.config.providers import infra_config
from app.infra.persistence.bootstrap import init_database


def create_import_app() -> FastAPI:
    app = FastAPI(title=infra_config.app.import_app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(infra_config.app.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_error_handlers(app)

    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(company.router)
    app.include_router(business_line.router)
    app.include_router(knowledge_base.router)
    app.include_router(document.router)
    app.include_router(model_config.router)
    app.include_router(playground.router)
    app.include_router(chat_session.router)
    app.include_router(query_widget.router)
    app.include_router(query_chat.router)

    mount_frontend(app)

    @app.on_event("startup")
    async def startup() -> None:
        init_database(seed=True)

    return app


app = create_import_app()
