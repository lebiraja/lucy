"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Central configuration for the Lucy backend."""

    # Database
    database_url: str = "postgresql+asyncpg://lucy:lucy_secret@db:5432/lucy_db"

    # Server
    backend_port: int = 8000
    frontend_port: int = 3000

    # CORS — allow frontend origin (override with CORS_ORIGINS env var, comma-separated)
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://localhost:2000",
        "http://127.0.0.1:2000",
        "http://localhost:2800",
        "http://127.0.0.1:2800",
    ]

    # vLLM defaults
    default_temperature: float = 0.7
    default_max_tokens: int = 2048
    default_top_p: float = 0.95

    # Timeouts (seconds)
    llm_request_timeout: float = 120.0
    health_check_timeout: float = 5.0
    heartbeat_timeout_seconds: int = 120
    heartbeat_check_interval: int = 60

    # Tool API keys
    serper_api_key: str = ""
    news_api_key: str = ""

    # Tool execution settings
    workspace_base_dir: str = "/tmp/lucy-workspace"
    code_execution_timeout: int = 30
    shell_execution_timeout: int = 10
    max_tool_iterations: int = 5

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
