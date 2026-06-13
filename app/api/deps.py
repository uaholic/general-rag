"""FastAPI 依赖注入。"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.infra.persistence.mysql import new_session


def get_db_session() -> Generator[Session, None, None]:
    """请求级 MySQL Session。"""
    session = new_session()
    try:
        yield session
    finally:
        session.close()
