from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Process Intelligence"
    database_url: str = "postgresql+psycopg2://pi:pi@localhost:5432/process_intelligence"
    # Maximum upload size accepted by the streaming CSV parser (bytes). Default 500 MB.
    max_upload_bytes: int = 500 * 1024 * 1024
    uploads_dir: str = "./data/uploads"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24

    # AI / LLM (Epic 6). When no api key/provider is set, AI features fall back
    # to deterministic behavior and report themselves as disabled.
    ai_provider: str = "none"  # none | openai | anthropic
    ai_model: str = "gpt-4o-mini"
    ai_request_timeout: float = 30.0
    openai_api_key: str = ""
    anthropic_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
