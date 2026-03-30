from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


_logger = logging.getLogger("uvicorn.error")
_MIGRATION_FILE_RE = re.compile(r"^(?P<version_number>\d{8,14})_(?P<name>[a-z0-9_]+)\.sql$")
_DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent / "versions"


@dataclass(frozen=True, slots=True)
class MigrationFile:
    identifier: str
    version_number: str
    name: str
    checksum: str
    sql: str
    path: Path


def discover_migrations(migrations_dir: Path | None = None) -> list[MigrationFile]:
    directory = migrations_dir or _DEFAULT_MIGRATIONS_DIR
    if not directory.exists():
        raise FileNotFoundError(f"Migration directory does not exist: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"Migration path is not a directory: {directory}")

    migrations: list[MigrationFile] = []
    seen_identifiers: set[str] = set()

    for path in sorted(directory.glob("*.sql")):
        match = _MIGRATION_FILE_RE.match(path.name)
        if not match:
            raise ValueError(
                "Invalid migration filename "
                f"{path.name!r}. Expected '<version>_<name>.sql' with lowercase snake_case."
            )

        identifier = path.stem
        if identifier in seen_identifiers:
            raise ValueError(f"Duplicate migration identifier found: {identifier}")
        seen_identifiers.add(identifier)

        sql = path.read_text(encoding="utf-8").strip()
        if not sql:
            raise ValueError(f"Migration file is empty: {path}")

        migrations.append(
            MigrationFile(
                identifier=identifier,
                version_number=match.group("version_number"),
                name=match.group("name"),
                checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                sql=sql,
                path=path,
            )
        )

    return migrations


async def apply_migrations(
    conn: AsyncConnection,
    migrations_dir: Path | None = None,
) -> None:
    migrations = discover_migrations(migrations_dir)
    await _ensure_schema_migrations_table(conn)

    result = await conn.execute(
        text(
            """
            SELECT version, version_number, name, checksum
            FROM schema_migrations
            """
        )
    )
    applied = {
        row.version: {
            "version_number": row.version_number,
            "name": row.name,
            "checksum": row.checksum,
        }
        for row in result
    }

    for migration in migrations:
        existing = applied.get(migration.identifier)
        if existing is not None:
            await _validate_or_backfill_migration_record(conn, migration, existing)
            continue

        statements = _split_sql_statements(migration.sql)
        if not statements:
            raise ValueError(f"Migration {migration.identifier} contains no executable SQL statements.")

        _logger.info("Applying DB migration: %s", migration.identifier)
        for statement in statements:
            await conn.exec_driver_sql(statement)

        await conn.execute(
            text(
                """
                INSERT INTO schema_migrations (version, version_number, name, checksum)
                VALUES (:version, :version_number, :name, :checksum)
                """
            ),
            {
                "version": migration.identifier,
                "version_number": migration.version_number,
                "name": migration.name,
                "checksum": migration.checksum,
            },
        )
        _logger.info("Applied DB migration: %s", migration.identifier)


async def _ensure_schema_migrations_table(conn: AsyncConnection) -> None:
    await conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(128) PRIMARY KEY,
            version_number VARCHAR(32),
            name VARCHAR(255),
            checksum VARCHAR(64),
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await conn.exec_driver_sql(
        "ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS version_number VARCHAR(32)"
    )
    await conn.exec_driver_sql(
        "ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS name VARCHAR(255)"
    )
    await conn.exec_driver_sql(
        "ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum VARCHAR(64)"
    )


async def _validate_or_backfill_migration_record(
    conn: AsyncConnection,
    migration: MigrationFile,
    existing: dict[str, str | None],
) -> None:
    checksum = existing.get("checksum")
    if checksum:
        if checksum != migration.checksum:
            raise RuntimeError(
                "Migration checksum mismatch for "
                f"{migration.identifier}. Refusing to continue because an applied SQL file changed."
            )
        if existing.get("version_number") and existing.get("name"):
            return

    await conn.execute(
        text(
            """
            UPDATE schema_migrations
            SET version_number = COALESCE(version_number, :version_number),
                name = COALESCE(name, :name),
                checksum = COALESCE(checksum, :checksum)
            WHERE version = :version
            """
        ),
        {
            "version": migration.identifier,
            "version_number": migration.version_number,
            "name": migration.name,
            "checksum": migration.checksum,
        },
    )


def _split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    i = 0
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False
    dollar_quote: str | None = None

    while i < len(sql):
        char = sql[i]
        next_char = sql[i + 1] if i + 1 < len(sql) else ""

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
                current.append(char)
            i += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if dollar_quote is not None:
            if sql.startswith(dollar_quote, i):
                current.append(dollar_quote)
                i += len(dollar_quote)
                dollar_quote = None
                continue
            current.append(char)
            i += 1
            continue

        if in_single_quote:
            current.append(char)
            if char == "'" and next_char == "'":
                current.append(next_char)
                i += 2
                continue
            if char == "'":
                in_single_quote = False
            i += 1
            continue

        if in_double_quote:
            current.append(char)
            if char == '"' and next_char == '"':
                current.append(next_char)
                i += 2
                continue
            if char == '"':
                in_double_quote = False
            i += 1
            continue

        if char == "-" and next_char == "-":
            in_line_comment = True
            i += 2
            continue

        if char == "/" and next_char == "*":
            in_block_comment = True
            i += 2
            continue

        if char == "'":
            in_single_quote = True
            current.append(char)
            i += 1
            continue

        if char == '"':
            in_double_quote = True
            current.append(char)
            i += 1
            continue

        if char == "$":
            tag_end = sql.find("$", i + 1)
            if tag_end != -1:
                candidate = sql[i : tag_end + 1]
                if re.fullmatch(r"\$[A-Za-z0-9_]*\$", candidate):
                    dollar_quote = candidate
                    current.append(candidate)
                    i = tag_end + 1
                    continue

        if char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            i += 1
            continue

        current.append(char)
        i += 1

    trailing_statement = "".join(current).strip()
    if trailing_statement:
        statements.append(trailing_statement)
    return statements
