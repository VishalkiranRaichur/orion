"""Safely stamp a legacy create_all database at the document baseline revision."""

import asyncio
from pathlib import Path

from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.config import settings

BASELINE_REVISION = "0001_document_baseline"
API_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_COLUMNS = {
    "documents": {
        "id",
        "filename",
        "content_type",
        "size_bytes",
        "storage_key",
        "status",
        "created_at",
    },
    "document_chunks": {
        "id",
        "document_id",
        "chunk_index",
        "content",
        "embedding",
    },
}


def inspect_schema(connection) -> str:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())

    if "alembic_version" in tables:
        return "versioned"

    present_baseline_tables = set(EXPECTED_COLUMNS) & tables
    if not present_baseline_tables:
        return "fresh"
    if present_baseline_tables != set(EXPECTED_COLUMNS):
        missing = sorted(set(EXPECTED_COLUMNS) - present_baseline_tables)
        raise RuntimeError(f"Legacy schema is incomplete; missing tables: {', '.join(missing)}")

    for table_name, expected_columns in EXPECTED_COLUMNS.items():
        actual_columns = set(
            connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :table_name"
                ),
                {"table_name": table_name},
            ).scalars()
        )
        if actual_columns != expected_columns:
            missing = sorted(expected_columns - actual_columns)
            extra = sorted(actual_columns - expected_columns)
            raise RuntimeError(
                f"Legacy table {table_name!r} does not match the baseline "
                f"(missing={missing}, extra={extra})."
            )

        primary_key = inspector.get_pk_constraint(table_name).get("constrained_columns")
        if primary_key != ["id"]:
            raise RuntimeError(f"Legacy table {table_name!r} does not have the expected ID key.")

    document_unique_constraints = inspector.get_unique_constraints("documents")
    if not any(
        constraint.get("column_names") == ["storage_key"]
        for constraint in document_unique_constraints
    ):
        raise RuntimeError("documents.storage_key is missing its unique constraint.")

    embedding_type = connection.execute(
        text(
            "SELECT format_type(attribute.atttypid, attribute.atttypmod) "
            "FROM pg_attribute AS attribute "
            "JOIN pg_class AS relation ON relation.oid = attribute.attrelid "
            "JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
            "WHERE namespace.nspname = 'public' "
            "AND relation.relname = 'document_chunks' "
            "AND attribute.attname = 'embedding'"
        )
    ).scalar_one_or_none()
    if embedding_type != "vector(1536)":
        raise RuntimeError("document_chunks.embedding is not a pgvector column.")

    document_foreign_keys = inspector.get_foreign_keys("document_chunks")
    if not any(
        key.get("referred_table") == "documents"
        and key.get("constrained_columns") == ["document_id"]
        for key in document_foreign_keys
    ):
        raise RuntimeError("document_chunks.document_id is missing its documents foreign key.")

    return "legacy"


async def inspect_database() -> str:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(inspect_schema)
    finally:
        await engine.dispose()


def main() -> None:
    state = asyncio.run(inspect_database())

    if state == "fresh":
        raise SystemExit("Database is empty; run `make db-upgrade` instead of baselining.")
    if state == "versioned":
        raise SystemExit("Database already has Alembic metadata; run `make db-upgrade`.")

    alembic_config = Config(API_ROOT / "alembic.ini")
    command.stamp(alembic_config, BASELINE_REVISION)
    print(f"Validated legacy schema and stamped {BASELINE_REVISION}.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        raise SystemExit(f"Refusing to stamp the legacy database: {error}") from error
