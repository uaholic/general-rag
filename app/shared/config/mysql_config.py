"""MySQL 配置。"""
from __future__ import annotations

from dataclasses import dataclass

from app.shared.config.common import env_bool, env_int, env_str


@dataclass(frozen=True)
class MySQLConfig:
    driver: str = env_str("MYSQL_DRIVER", "mysql+pymysql")
    host: str = env_str("MYSQL_HOST", "127.0.0.1")
    port: int = env_int("MYSQL_PORT", 3306)
    user: str = env_str("MYSQL_USER", "root")
    password: str = env_str("MYSQL_PASSWORD", "")
    database: str = env_str("MYSQL_DATABASE", "enterprise_rag")
    charset: str = env_str("MYSQL_CHARSET", "utf8mb4")
    echo: bool = env_bool("MYSQL_ECHO", False)
    pool_size: int = env_int("MYSQL_POOL_SIZE", 5)
    max_overflow: int = env_int("MYSQL_MAX_OVERFLOW", 10)
    pool_recycle: int = env_int("MYSQL_POOL_RECYCLE", 3600)


mysql_config = MySQLConfig()
