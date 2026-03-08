from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api: str = Field(default="", validation_alias=AliasChoices("GROQ_API", "GROQ_API_KEY"))
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    youtube_api_key: str = Field(default="", alias="YOUTUBE_API_KEY")
    enable_crewai_execution: bool = Field(default=False, alias="ENABLE_CREWAI_EXECUTION")
    enable_fallback_content: bool = Field(default=False, alias="ENABLE_FALLBACK_CONTENT")
    material_output_dir: Path = Field(
        default=Path("output/study_material"),
        alias="MATERIAL_OUTPUT_DIR",
    )
    max_parallel_concepts: int = Field(default=3, alias="MAX_PARALLEL_CONCEPTS")
    llm_max_concurrency: int = Field(default=1, alias="LLM_MAX_CONCURRENCY")
    agent_retry_attempts: int = Field(default=3, alias="AGENT_RETRY_ATTEMPTS")
    max_revision_cycles: int = Field(default=2, alias="MAX_REVISION_CYCLES")
    request_timeout_seconds: int = Field(default=30, alias="REQUEST_TIMEOUT_SECONDS")
    resource_search_timeout_seconds: int = Field(default=8, alias="RESOURCE_SEARCH_TIMEOUT_SECONDS")
    resource_validation_timeout_seconds: int = Field(default=4, alias="RESOURCE_VALIDATION_TIMEOUT_SECONDS")
    allow_resourceless_generation: bool = Field(default=True, alias="ALLOW_RESOURCELESS_GENERATION")
    evidence_search_results_per_query: int = Field(default=3, alias="EVIDENCE_SEARCH_RESULTS_PER_QUERY")
    evidence_max_sources: int = Field(default=6, alias="EVIDENCE_MAX_SOURCES")
    evidence_max_snippets: int = Field(default=10, alias="EVIDENCE_MAX_SNIPPETS")
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
    postgres_user: str = Field(default="postgres", alias="POSTGRES_USER")
    postgres_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    jwt_secret: str = Field(min_length=16, alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_exp_minutes: int = Field(default=60, alias="JWT_EXP_MINUTES")

    def ensure_output_dir(self) -> None:
        self.material_output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def database_url(self) -> str:
        if self.postgres_url:
            return self.postgres_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_output_dir()
    return settings
