from dataclasses import dataclass

from app.shared.config.common import env_int, env_str


@dataclass
class AppSettings:
    import_app_name: str = env_str("IMPORT_APP_NAME", "Enterprise RAG Import Service")
    query_app_name: str = env_str("QUERY_APP_NAME", "Enterprise RAG Query Service")
    app_env: str = env_str("APP_ENV", "dev")
    app_host: str = env_str("APP_HOST", "0.0.0.0")
    import_app_port: int = env_int("IMPORT_APP_PORT", 8000)
    query_app_port: int = env_int("QUERY_APP_PORT", 8001)
    cors_origins: tuple[str, ...] = tuple(
        item.strip() for item in env_str("CORS_ORIGINS", "*").split(",") if item.strip()
    )

settings = AppSettings()
