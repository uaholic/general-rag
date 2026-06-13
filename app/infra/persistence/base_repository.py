"""通用 Repository 基类。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.infra.persistence.mysql import Base


ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """封装常见 CRUD，具体仓库继承后指定 model。"""

    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, pk: Any) -> ModelT | None:
        return self.session.get(self.model, pk)

    def list_all(self) -> list[ModelT]:
        return list(self.session.scalars(select(self.model)).all())

    def list_by_statement(self, statement: Select[tuple[ModelT]]) -> list[ModelT]:
        return list(self.session.scalars(statement).all())

    def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        self.session.flush()
        return instance

    def delete(self, instance: ModelT) -> None:
        self.session.delete(instance)

    def flush(self) -> None:
        self.session.flush()
