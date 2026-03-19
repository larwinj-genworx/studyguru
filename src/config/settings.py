from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlencode

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api: str = Field(default="", validation_alias=AliasChoices("GROQ_API", "GROQ_API_KEY"))
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    groq_api_base_url: str = Field(default="https://api.groq.com/openai/v1", alias="GROQ_API_BASE_URL")
    youtube_api_key: str = Field(default="", alias="YOUTUBE_API_KEY")
    youtube_api_base_url: str = Field(
        default="https://www.googleapis.com/youtube/v3",
        alias="YOUTUBE_API_BASE_URL",
    )
    enable_crewai_execution: bool = Field(default=False, alias="ENABLE_CREWAI_EXECUTION")
    enable_fallback_content: bool = Field(default=False, alias="ENABLE_FALLBACK_CONTENT")
    material_output_dir: Path = Field(
        default=Path("output/study_material"),
        alias="MATERIAL_OUTPUT_DIR",
    )
    artifact_storage_backend: Literal["local", "gcs"] = Field(
        default="gcs",
        alias="ARTIFACT_STORAGE_BACKEND",
    )
    gcs_project_id: str = Field(default="", alias="GCS_PROJECT_ID")
    gcs_bucket_name: str = Field(default="", alias="GCS_BUCKET_NAME")
    gcs_bucket_prefix: str = Field(default="", alias="GCS_BUCKET_PREFIX")
    gcs_target_service_account: str = Field(
        default="",
        alias="GCS_TARGET_SERVICE_ACCOUNT",
    )
    gcs_request_timeout_seconds: int = Field(default=300, alias="GCS_REQUEST_TIMEOUT_SECONDS")
    gcs_upload_workers: int = Field(default=8, alias="GCS_UPLOAD_WORKERS")
    max_parallel_concepts: int = Field(default=3, alias="MAX_PARALLEL_CONCEPTS")
    llm_max_concurrency: int = Field(default=1, alias="LLM_MAX_CONCURRENCY")
    llm_cache_ttl_seconds: int = Field(default=300, alias="LLM_CACHE_TTL_SECONDS")
    llm_cache_max_entries: int = Field(default=128, alias="LLM_CACHE_MAX_ENTRIES")
    agent_retry_attempts: int = Field(default=3, alias="AGENT_RETRY_ATTEMPTS")
    max_revision_cycles: int = Field(default=2, alias="MAX_REVISION_CYCLES")
    request_timeout_seconds: int = Field(default=30, alias="REQUEST_TIMEOUT_SECONDS")
    llm_healthcheck_timeout_seconds: float = Field(
        default=5.0,
        alias="LLM_HEALTHCHECK_TIMEOUT_SECONDS",
    )
    resource_search_timeout_seconds: int = Field(default=8, alias="RESOURCE_SEARCH_TIMEOUT_SECONDS")
    resource_validation_timeout_seconds: int = Field(default=4, alias="RESOURCE_VALIDATION_TIMEOUT_SECONDS")
    resource_cache_ttl_seconds: int = Field(default=300, alias="RESOURCE_CACHE_TTL_SECONDS")
    resource_cache_max_entries: int = Field(default=256, alias="RESOURCE_CACHE_MAX_ENTRIES")
    allow_resourceless_generation: bool = Field(default=True, alias="ALLOW_RESOURCELESS_GENERATION")
    evidence_search_results_per_query: int = Field(default=3, alias="EVIDENCE_SEARCH_RESULTS_PER_QUERY")
    evidence_max_sources: int = Field(default=6, alias="EVIDENCE_MAX_SOURCES")
    evidence_max_snippets: int = Field(default=10, alias="EVIDENCE_MAX_SNIPPETS")
    concept_visual_output_dir: Path = Field(
        default=Path("output/concept_visuals"),
        validation_alias=AliasChoices("CONCEPT_VISUAL_OUTPUT_DIR", "CONCEPT_IMAGE_OUTPUT_DIR"),
    )
    concept_visual_service_url: str = Field(
        default="",
        alias="CONCEPT_VISUAL_SERVICE_URL",
    )
    concept_visual_service_token: str = Field(
        default="",
        alias="CONCEPT_VISUAL_SERVICE_TOKEN",
    )
    concept_visual_request_timeout_seconds: int = Field(
        default=20,
        alias="CONCEPT_VISUAL_REQUEST_TIMEOUT_SECONDS",
    )
    concept_visual_local_output_dir: Path = Field(
        default=Path("../StudyGuru_ConceptVisualBackend/output/concept_visuals"),
        alias="CONCEPT_VISUAL_LOCAL_OUTPUT_DIR",
    )
    concept_image_max_candidates: int = Field(default=3, alias="CONCEPT_IMAGE_MAX_CANDIDATES")
    concept_image_min_width: int = Field(default=960, alias="CONCEPT_IMAGE_MIN_WIDTH")
    concept_image_min_height: int = Field(default=540, alias="CONCEPT_IMAGE_MIN_HEIGHT")
    learning_bot_history_limit: int = Field(default=8, alias="LEARNING_BOT_HISTORY_LIMIT")
    learning_bot_max_internal_chunks: int = Field(default=6, alias="LEARNING_BOT_MAX_INTERNAL_CHUNKS")
    learning_bot_max_external_chunks: int = Field(default=4, alias="LEARNING_BOT_MAX_EXTERNAL_CHUNKS")
    learning_bot_external_trigger_score: float = Field(
        default=0.17,
        alias="LEARNING_BOT_EXTERNAL_TRIGGER_SCORE",
    )

    quiz_min_questions: int = Field(default=10, alias="QUIZ_MIN_QUESTIONS")
    quiz_max_questions: int = Field(default=30, alias="QUIZ_MAX_QUESTIONS")
    quiz_base_questions: int = Field(default=8, alias="QUIZ_BASE_QUESTIONS")
    quiz_per_topic_questions: int = Field(default=2, alias="QUIZ_PER_TOPIC_QUESTIONS")
    quiz_complexity_multiplier: float = Field(default=0.6, alias="QUIZ_COMPLEXITY_MULTIPLIER")
    quiz_bank_buffer: int = Field(default=2, alias="QUIZ_BANK_BUFFER")
    quiz_max_hints: int = Field(default=3, alias="QUIZ_MAX_HINTS")

    postgres_url: str = Field(default="", alias="POSTGRES_URL")
    postgres_db: str = Field(default="postgres", alias="POSTGRES_DB")
    postgres_user: str = Field(default="", alias="POSTGRES_USER")
    postgres_password: str = Field(default="", alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_instance_connection_name: str = Field(
        default="",
        alias="POSTGRES_INSTANCE_CONNECTION_NAME",
    )
    postgres_socket_dir: str = Field(default="/cloudsql", alias="POSTGRES_SOCKET_DIR")

    jwt_secret: str = Field(min_length=16, alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_exp_minutes: int = Field(default=60, alias="JWT_EXP_MINUTES")
    auth_cookie_name: str = Field(default="studyguru_access_token", alias="AUTH_COOKIE_NAME")
    auth_cookie_domain: str = Field(default="", alias="AUTH_COOKIE_DOMAIN")
    auth_cookie_secure: bool = Field(default=True, alias="AUTH_COOKIE_SECURE")
    auth_cookie_samesite: Literal["lax", "strict", "none"] = Field(
        default="lax",
        alias="AUTH_COOKIE_SAMESITE",
    )
    cors_allow_origins_raw: str = Field(
        default="",
        alias="CORS_ALLOW_ORIGINS",
    )
    log_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = Field(
        default="INFO",
        alias="LOG_LEVEL",
    )

    def ensure_output_dir(self) -> None:
        self.material_output_dir.mkdir(parents=True, exist_ok=True)
        self.concept_visual_output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def gcs_enabled(self) -> bool:
        return self.artifact_storage_backend == "gcs"

    @property
    def cors_allow_origins(self) -> list[str]:
        return [
            origin.rstrip("/")
            for origin in (item.strip() for item in self.cors_allow_origins_raw.split(","))
            if origin
        ]

    @property
    def database_url(self) -> str:
        cloudsql_socket_host = self.cloudsql_socket_host
        if cloudsql_socket_host:
            return self._build_cloudsql_socket_database_url(cloudsql_socket_host)
        if self.postgres_url:
            return self.postgres_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cloudsql_socket_host(self) -> str:
        if self.postgres_instance_connection_name:
            return f"{self.postgres_socket_dir.rstrip('/')}/{self.postgres_instance_connection_name}"
        if self.postgres_host.startswith("/cloudsql/"):
            return self.postgres_host
        return ""

    @property
    def groq_models_url(self) -> str:
        return f"{self.groq_api_base_url.rstrip('/')}/models"

    @property
    def youtube_search_url(self) -> str:
        return f"{self.youtube_api_base_url.rstrip('/')}/search"

    @property
    def youtube_videos_url(self) -> str:
        return f"{self.youtube_api_base_url.rstrip('/')}/videos"

    @property
    def youtube_watch_base_url(self) -> str:
        return "https://www.youtube.com/watch"

    def _build_cloudsql_socket_database_url(self, socket_host: str) -> str:
        username = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password, safe="")
        database = quote(self.postgres_db, safe="")
        query = urlencode({"host": socket_host})
        return f"postgresql+asyncpg://{username}:{password}@/{database}?{query}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_output_dir()
    return settings
