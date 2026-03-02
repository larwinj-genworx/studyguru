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
