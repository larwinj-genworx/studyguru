from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import get_settings
from src.data.models.postgres.base import Base
from src.data.models.postgres import models  # noqa: F401


_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    pool_pre_ping=True,
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

_logger = logging.getLogger("uvicorn.error")

_MIGRATIONS: list[tuple[str, list[str]]] = [
    (
        "20260302_add_learning_content_columns",
        [
            "ALTER TABLE concept_materials ADD COLUMN IF NOT EXISTS content JSONB",
            "ALTER TABLE concept_materials ADD COLUMN IF NOT EXISTS content_text TEXT",
            "ALTER TABLE concept_materials ADD COLUMN IF NOT EXISTS content_schema_version VARCHAR(24) DEFAULT 'v1'",
            "ALTER TABLE concept_materials ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
            "UPDATE concept_materials SET updated_at = generated_at WHERE updated_at IS NULL",
            """
            CREATE TABLE IF NOT EXISTS concept_bookmarks (
                user_id VARCHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                concept_id VARCHAR(32) NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, concept_id)
            )
            """,
        ],
    ),
    (
        "20260302_fix_content_text_index",
        [
            "DROP INDEX IF EXISTS ix_concept_materials_content_text",
            "CREATE INDEX IF NOT EXISTS ix_concept_materials_content_text_fts ON concept_materials USING GIN (to_tsvector('english', content_text))",
        ],
    ),
    (
        "20260302_add_concept_video_feedback",
        [
            """
            CREATE TABLE IF NOT EXISTS concept_video_feedback (
                concept_id VARCHAR(32) NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
                video_id VARCHAR(32) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'rejected',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (concept_id, video_id)
            )
            """
        ],
    ),
    (
        "20260305_add_quiz_tables",
        [
            """
            CREATE TABLE IF NOT EXISTS quiz_questions (
                id VARCHAR(32) PRIMARY KEY,
                subject_id VARCHAR(32) NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
                concept_id VARCHAR(32) NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
                material_version INTEGER NOT NULL,
                question TEXT NOT NULL,
                options JSONB NOT NULL DEFAULT '[]'::jsonb,
                correct_option TEXT NOT NULL,
                hints JSONB NOT NULL DEFAULT '[]'::jsonb,
                explanation TEXT,
                difficulty VARCHAR(20) NOT NULL DEFAULT 'medium',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_quiz_questions_concept_version ON quiz_questions (concept_id, material_version)",
            "CREATE INDEX IF NOT EXISTS ix_quiz_questions_subject ON quiz_questions (subject_id)",
            """
            CREATE TABLE IF NOT EXISTS quiz_sessions (
                id VARCHAR(32) PRIMARY KEY,
                user_id VARCHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                subject_id VARCHAR(32) NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
                status VARCHAR(20) NOT NULL DEFAULT 'in_progress',
                concept_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                question_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                current_index INTEGER NOT NULL DEFAULT 0,
                total_questions INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                incorrect_count INTEGER NOT NULL DEFAULT 0,
                score_percent DOUBLE PRECISION,
                session_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
                report JSONB,
                started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_quiz_sessions_user ON quiz_sessions (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_quiz_sessions_subject ON quiz_sessions (subject_id)",
            """
            CREATE TABLE IF NOT EXISTS quiz_responses (
                id VARCHAR(32) PRIMARY KEY,
                session_id VARCHAR(32) NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
                question_id VARCHAR(32) NOT NULL REFERENCES quiz_questions(id) ON DELETE CASCADE,
                concept_id VARCHAR(32) NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
                selected_option TEXT,
                is_correct BOOLEAN NOT NULL DEFAULT FALSE,
                attempts INTEGER NOT NULL DEFAULT 0,
                hints_used INTEGER NOT NULL DEFAULT 0,
                attempt_log JSONB NOT NULL DEFAULT '[]'::jsonb,
                answered_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (session_id, question_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_quiz_responses_session ON quiz_responses (session_id)",
            "CREATE INDEX IF NOT EXISTS ix_quiz_responses_concept ON quiz_responses (concept_id)",
        ],
    ),
    (
        "20260307_relax_quiz_fks",
        [
            "ALTER TABLE quiz_questions DROP CONSTRAINT IF EXISTS quiz_questions_subject_id_fkey",
            "ALTER TABLE quiz_questions DROP CONSTRAINT IF EXISTS quiz_questions_concept_id_fkey",
            "ALTER TABLE quiz_sessions DROP CONSTRAINT IF EXISTS quiz_sessions_subject_id_fkey",
            "ALTER TABLE quiz_responses DROP CONSTRAINT IF EXISTS quiz_responses_concept_id_fkey",
            "ALTER TABLE quiz_questions ALTER COLUMN subject_id DROP NOT NULL",
            "ALTER TABLE quiz_questions ALTER COLUMN concept_id DROP NOT NULL",
            "ALTER TABLE quiz_sessions ALTER COLUMN subject_id DROP NOT NULL",
            "ALTER TABLE quiz_responses ALTER COLUMN concept_id DROP NOT NULL",
            """
            ALTER TABLE quiz_questions
            ADD CONSTRAINT quiz_questions_subject_id_fkey
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL
            """,
            """
            ALTER TABLE quiz_questions
            ADD CONSTRAINT quiz_questions_concept_id_fkey
            FOREIGN KEY (concept_id) REFERENCES concepts(id) ON DELETE SET NULL
            """,
            """
            ALTER TABLE quiz_sessions
            ADD CONSTRAINT quiz_sessions_subject_id_fkey
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL
            """,
            """
            ALTER TABLE quiz_responses
            ADD CONSTRAINT quiz_responses_concept_id_fkey
            FOREIGN KEY (concept_id) REFERENCES concepts(id) ON DELETE SET NULL
            """,
        ],
    ),
]


async def _apply_migrations(conn) -> None:
    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(64) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    result = await conn.execute(text("SELECT version FROM schema_migrations"))
    applied = {row[0] for row in result.fetchall()}
    for version, statements in _MIGRATIONS:
        if version in applied:
            continue
        for statement in statements:
            await conn.execute(text(statement))
        await conn.execute(
            text("INSERT INTO schema_migrations (version) VALUES (:version) ON CONFLICT DO NOTHING"),
            {"version": version},
        )
        _logger.info("Applied DB migration: %s", version)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _apply_migrations(conn)
