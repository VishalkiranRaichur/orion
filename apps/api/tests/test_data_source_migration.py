from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from app.config import settings
from app.demo.orion_importer import import_orion_company
from app.models import DEMO_DATA_SOURCE_ID, DEMO_WORKSPACE_ID

DEMO_ROOT = Path(__file__).resolve().parents[3] / "demo" / "orion_company"


def _database_url(database: str) -> str:
    return make_url(settings.database_url).set(database=database).render_as_string(
        hide_password=False
    )


def _asyncpg_url(database: str) -> str:
    return _database_url(database).replace("postgresql+asyncpg://", "postgresql://", 1)


async def _database_available() -> bool:
    try:
        connection = await asyncpg.connect(_asyncpg_url(make_url(settings.database_url).database))
    except (OSError, asyncpg.PostgresError):
        return False
    await connection.close()
    return True


async def _create_database(database: str) -> None:
    admin_database = make_url(settings.database_url).database
    connection = await asyncpg.connect(_asyncpg_url(admin_database))
    try:
        await connection.execute(f'CREATE DATABASE "{database}"')
    finally:
        await connection.close()
    connection = await asyncpg.connect(_asyncpg_url(database))
    try:
        await connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        await connection.close()


async def _drop_database(database: str) -> None:
    admin_database = make_url(settings.database_url).database
    connection = await asyncpg.connect(_asyncpg_url(admin_database))
    try:
        await connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database,
        )
        await connection.execute(f'DROP DATABASE IF EXISTS "{database}"')
    finally:
        await connection.close()


def _alembic_config(database: str) -> Config:
    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))
    settings.database_url = _database_url(database)
    return config


@contextmanager
def temporary_database() -> Iterator[tuple[str, Config]]:
    if not asyncio.run(_database_available()):
        if os.environ.get("ORION_REQUIRE_POSTGRES") == "1":
            pytest.fail("PostgreSQL is required (ORION_REQUIRE_POSTGRES=1) but is not reachable")
        pytest.skip("PostgreSQL is not available for migration integration tests")
    original_url = settings.database_url
    database = f"orion_migration_{uuid.uuid4().hex}"
    try:
        asyncio.run(_create_database(database))
        yield database, _alembic_config(database)
    finally:
        settings.database_url = original_url
        asyncio.run(_drop_database(database))


async def _seed_phase_four_documents(database: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    private_workspace_id = uuid.uuid4()
    demo_document_id = uuid.uuid4()
    private_document_id = uuid.uuid4()
    connection = await asyncpg.connect(_asyncpg_url(database))
    try:
        await connection.execute(
            """INSERT INTO workspaces
               (id, name, industry, owner_subject, is_demo, created_at, updated_at)
               VALUES ($1, 'Private', NULL, 'user-a', false, now(), now())""",
            private_workspace_id,
        )
        await connection.executemany(
            """INSERT INTO documents
               (id, workspace_id, filename, content_type, size_bytes, storage_key,
                status, created_at)
               VALUES ($1, $2, $3, 'text/plain', 4, $4, 'processed', now())""",
            [
                (
                    demo_document_id,
                    DEMO_WORKSPACE_ID,
                    "demo.txt",
                    "demo/orion_company/demo.txt",
                ),
                (
                    private_document_id,
                    private_workspace_id,
                    "private.txt",
                    f"workspaces/{private_workspace_id}/documents/{private_document_id}/private.txt",
                ),
            ],
        )
    finally:
        await connection.close()
    return private_workspace_id, demo_document_id, private_document_id


def test_upgrade_populated_phase_four_database_to_data_source_foundation() -> None:
    with temporary_database() as (database, config):
        command.upgrade(config, "0004_workspace_isolation")
        private_workspace_id, demo_document_id, private_document_id = asyncio.run(
            _seed_phase_four_documents(database)
        )
        command.upgrade(config, "head")

        async def assert_state() -> None:
            connection = await asyncpg.connect(_asyncpg_url(database))
            try:
                source = await connection.fetchrow(
                    "SELECT * FROM data_sources WHERE id = $1", DEMO_DATA_SOURCE_ID
                )
                assert source is not None
                assert source["workspace_id"] == DEMO_WORKSPACE_ID
                assert source["source_type"] == "demo"
                assert source["last_synced_at"] is not None
                assert await connection.fetchval(
                    "SELECT data_source_id FROM documents WHERE id = $1", demo_document_id
                ) == DEMO_DATA_SOURCE_ID
                assert (
                    await connection.fetchval(
                        "SELECT data_source_id FROM documents WHERE id = $1",
                        private_document_id,
                    )
                    is None
                )
                private_source_id = uuid.uuid4()
                await connection.execute(
                    """INSERT INTO data_sources
                       (id, workspace_id, name, source_type, status, created_at, updated_at)
                       VALUES ($1, $2, 'Private Uploads', 'upload', 'ready', now(), now())""",
                    private_source_id,
                    private_workspace_id,
                )
                with pytest.raises(asyncpg.ForeignKeyViolationError):
                    await connection.execute(
                        "UPDATE documents SET data_source_id = $1 WHERE id = $2",
                        private_source_id,
                        demo_document_id,
                    )
            finally:
                await connection.close()

        asyncio.run(assert_state())


def test_upgrade_fresh_database_and_alembic_schema_check() -> None:
    with temporary_database() as (database, config):
        command.upgrade(config, "head")
        command.check(config)

        async def assert_state() -> None:
            connection = await asyncpg.connect(_asyncpg_url(database))
            try:
                assert await connection.fetchval(
                    "SELECT count(*) FROM data_sources WHERE id = $1", DEMO_DATA_SOURCE_ID
                ) == 1
                assert await connection.fetchval(
                    "SELECT last_synced_at FROM data_sources WHERE id = $1",
                    DEMO_DATA_SOURCE_ID,
                ) is None
                assert await connection.fetchval("SELECT count(*) FROM documents") == 0
            finally:
                await connection.close()

        asyncio.run(assert_state())


def test_demo_import_is_idempotent_and_does_not_touch_private_sources() -> None:
    with temporary_database() as (database, config):
        command.upgrade(config, "head")

        async def run_imports() -> tuple[dict[str, int], dict[str, int], uuid.UUID]:
            engine = create_async_engine(_database_url(database))
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            private_workspace_id = uuid.uuid4()
            private_source_id = uuid.uuid4()
            private_document_id = uuid.uuid4()
            async with session_factory() as db:
                await db.execute(
                    text(
                        """INSERT INTO workspaces
                           (id, name, owner_subject, is_demo, created_at, updated_at)
                           VALUES (:id, 'Private', 'user-a', false, now(), now())"""
                    ),
                    {"id": private_workspace_id},
                )
                await db.execute(
                    text(
                        """INSERT INTO data_sources
                           (id, workspace_id, name, source_type, status, created_at, updated_at)
                           VALUES (:id, :workspace_id, 'Private Uploads', 'upload', 'ready',
                                   now(), now())"""
                    ),
                    {"id": private_source_id, "workspace_id": private_workspace_id},
                )
                await db.execute(
                    text(
                        """INSERT INTO documents
                           (id, workspace_id, data_source_id, filename, content_type, size_bytes,
                            storage_key, status, created_at)
                           VALUES (:id, :workspace_id, :source_id, 'private.txt', 'text/plain', 4,
                                   :storage_key, 'processed', now())"""
                    ),
                    {
                        "id": private_document_id,
                        "workspace_id": private_workspace_id,
                        "source_id": private_source_id,
                        "storage_key": (
                            f"workspaces/{private_workspace_id}/documents/"
                            f"{private_document_id}/private.txt"
                        ),
                    },
                )
                await db.commit()

            async def processor(file_bytes: bytes, _filename: str) -> dict:
                return {
                    "chunks": [file_bytes.decode()],
                    "embeddings": [[0.0] * 1536],
                }

            def upload(_content: bytes, storage_key: str, _content_type: str) -> str:
                return storage_key

            async with session_factory() as db:
                first = await import_orion_company(
                    db,
                    DEMO_ROOT,
                    upload=upload,
                    delete=lambda _key: None,
                    processor=processor,
                )
            async with session_factory() as db:
                second = await import_orion_company(
                    db,
                    DEMO_ROOT,
                    upload=upload,
                    delete=lambda _key: None,
                    processor=processor,
                )
            await engine.dispose()
            return first, second, private_source_id

        first, second, private_source_id = asyncio.run(run_imports())
        assert first == second

        async def assert_state() -> None:
            connection = await asyncpg.connect(_asyncpg_url(database))
            try:
                assert await connection.fetchval(
                    "SELECT count(*) FROM data_sources WHERE id = $1", DEMO_DATA_SOURCE_ID
                ) == 1
                assert await connection.fetchval(
                    """SELECT count(*) FROM documents
                       WHERE workspace_id = $1 AND data_source_id IS DISTINCT FROM $2""",
                    DEMO_WORKSPACE_ID,
                    DEMO_DATA_SOURCE_ID,
                ) == 0
                assert await connection.fetchval(
                    "SELECT count(*) FROM documents WHERE workspace_id = $1",
                    DEMO_WORKSPACE_ID,
                ) == first["documents"]
                assert await connection.fetchval(
                    "SELECT count(*) FROM document_chunks WHERE workspace_id = $1",
                    DEMO_WORKSPACE_ID,
                ) == first["documents"]
                assert await connection.fetchval(
                    "SELECT count(*) FROM data_sources WHERE id = $1 AND status = 'ready'",
                    private_source_id,
                ) == 1
                assert await connection.fetchval(
                    "SELECT count(*) FROM documents WHERE workspace_id <> $1",
                    DEMO_WORKSPACE_ID,
                ) == 1
            finally:
                await connection.close()

        asyncio.run(assert_state())
