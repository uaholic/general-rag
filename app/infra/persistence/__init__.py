"""持久化基础设施统一出口。"""
from app.infra.persistence.base_repository import BaseRepository
from app.infra.persistence.bootstrap import init_database
from app.infra.persistence.mysql import (
    Base,
    build_mysql_url,
    dispose_engine,
    get_engine,
    get_session_factory,
    new_session,
    session_scope,
)

__all__ = [
    "Base",
    "BaseRepository",
    "build_mysql_url",
    "dispose_engine",
    "get_engine",
    "get_session_factory",
    "init_database",
    "new_session",
    "session_scope",
]
