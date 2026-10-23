from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest

from alembic import command
from tests.test_data_source_migration import (
    _asyncpg_url,
    _seed_phase_four_documents,
    temporary_database,
)


async def _associate_checkpoint_two_documents(
    database: str,
    private_workspace_id: uuid.UUID,
    demo_document_id: uuid.UUID,
    private_document_id: uuid.UUID,
) -> uuid.UUID:
    private_source_id = uuid.uuid4()
    connection = await asyncpg.connect(_asyncpg_url(database))
    try:
        await connection.execute(
            """INSERT INTO data_sources
               (id, workspace_id, name, source_type, status, created_at, updated_at)
               VALUES ($1, $2, 'Private Uploads', 'upload', 'ready', now(), now())""",
            private_source_id,
            private_workspace_id,
        )
        await connection.execute(
            """UPDATE documents
               SET data_source_id = CASE
                 WHEN id = $1 THEN 'f42e7ff6-554b-5085-829f-ae80983bcc38'::uuid
                 WHEN id = $2 THEN $3
               END
               WHERE id IN ($1, $2)""",
            demo_document_id,
            private_document_id,
            private_source_id,
        )
    finally:
        await connection.close()
    return private_source_id


def test_upgrade_populated_checkpoint_two_database_preserves_existing_documents() -> None:
    with temporary_database() as (database, config):
        command.upgrade(config, "0005_data_source_foundation")
        private_workspace_id, demo_document_id, private_document_id = asyncio.run(
            _seed_phase_four_documents(database)
        )
        private_source_id = asyncio.run(
            _associate_checkpoint_two_documents(
                database,
                private_workspace_id,
                demo_document_id,
                private_document_id,
            )
        )
        command.upgrade(config, "head")

        async def assert_state() -> None:
            connection = await asyncpg.connect(_asyncpg_url(database))
            try:
                assert await connection.fetchval("SELECT version_num FROM alembic_version") == (
                    "0006_source_import_pipeline"
                )
                for document_id in (demo_document_id, private_document_id):
                    document = await connection.fetchrow(
                        """SELECT source_item_id, source_modified_at, source_synced_at,
                                  content_sha256
                           FROM documents WHERE id = $1""",
                        document_id,
                    )
                    assert document is not None
                    assert all(value is None for value in document.values())
                assert await connection.fetchval(
                    "SELECT data_source_id FROM documents WHERE id = $1",
                    private_document_id,
                ) == private_source_id

                source_id = uuid.uuid4()
                await connection.execute(
                    """INSERT INTO data_sources
                       (id, workspace_id, name, source_type, status, created_at, updated_at)
                       VALUES ($1, $2, 'Local Fixture', 'local_fixture', 'ready', now(), now())""",
                    source_id,
                    private_workspace_id,
                )
                document_id = uuid.uuid4()
                await connection.execute(
                    """INSERT INTO documents
                       (id, workspace_id, data_source_id, source_item_id, source_synced_at,
                        content_sha256, filename, content_type, size_bytes, storage_key,
                        status, created_at)
                       VALUES ($1, $2, $3, 'item-1', now(), $4, 'item.txt', 'text/plain', 4,
                               $5, 'processed', now())""",
                    document_id,
                    private_workspace_id,
                    source_id,
                    "a" * 64,
                    f"workspaces/{private_workspace_id}/documents/{document_id}/item.txt",
                )
                duplicate_id = uuid.uuid4()
                with pytest.raises(asyncpg.UniqueViolationError):
                    await connection.execute(
                        """INSERT INTO documents
                           (id, workspace_id, data_source_id, source_item_id, filename,
                            content_type, size_bytes, storage_key, status, created_at)
                           VALUES ($1, $2, $3, 'item-1', 'duplicate.txt', 'text/plain', 4,
                                   $4, 'processed', now())""",
                        duplicate_id,
                        private_workspace_id,
                        source_id,
                        f"workspaces/{private_workspace_id}/documents/{duplicate_id}/duplicate.txt",
                    )
            finally:
                await connection.close()

        asyncio.run(assert_state())


def test_fresh_database_reaches_source_import_head_without_schema_drift() -> None:
    with temporary_database() as (database, config):
        command.upgrade(config, "head")
        command.check(config)

        async def current_revision() -> str | None:
            connection = await asyncpg.connect(_asyncpg_url(database))
            try:
                return await connection.fetchval("SELECT version_num FROM alembic_version")
            finally:
                await connection.close()

        assert asyncio.run(current_revision()) == "0006_source_import_pipeline"
