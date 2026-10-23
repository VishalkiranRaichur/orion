from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Admin AI API"
    debug: bool = False
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://adminai:adminai@localhost:5432/adminai"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "admin-ai-documents"
    s3_region: str = "us-east-1"

    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    chat_model: str = "gpt-4o-mini"
    structured_response_model: str = "gpt-4o-mini"
    max_upload_size_mb: int = 20

    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    investigation_max_steps: int = 8
    investigation_max_model_calls: int = 6
    investigation_max_retrieval_calls: int = 6
    investigation_max_runtime_seconds: int = 300
    investigations_enabled: bool = True
    investigation_planner_mode: str = "model"

    orion_auth_mode: str = "local"
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
