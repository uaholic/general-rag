"""SQLAlchemy / MySQL 基础设施。"""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.infra.config.providers import infra_config


class Base(DeclarativeBase):
    """所有 SQLAlchemy ORM 模型的基类。"""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def build_mysql_url() -> URL:
    """根据环境变量构造 MySQL 连接 URL。"""
    config = infra_config.mysql
    return URL.create(
        drivername=config.driver,
        username=config.user,
        password=config.password or None,
        host=config.host,
        port=config.port,
        database=config.database,
        query={"charset": config.charset},
    )


def get_engine() -> Engine:
    """获取全局 Engine，首次调用时懒加载。"""
    global _engine
    if _engine is None:
        config = infra_config.mysql
        _engine = create_engine(
            build_mysql_url(),
            echo=config.echo,
            pool_pre_ping=True,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_recycle=config.pool_recycle,
            future=True,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """获取 SQLAlchemy Session 工厂。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            class_=Session,
        )
    return _session_factory


def new_session() -> Session:
    """创建一个新的数据库 Session。"""
    return get_session_factory()()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """命令行脚本和后台任务可复用的事务上下文。"""
    session = new_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engine() -> None:
    """测试或进程退出时释放连接池。"""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
