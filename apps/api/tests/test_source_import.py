from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.services.document_ingestion as document_ingestion
import app.services.rag_service as rag_service
import app.services.search_service as search_service
from alembic import command
from app.models import DEMO_WORKSPACE_ID, DataSource, Document, DocumentChunk, Workspace
from app.services.local_fixture_importer import (
    LocalFixtureImporter,
    ensure_local_fixture_source,
)
from app.services.source_import import (
    NormalizedIngestionItem,
    import_from_source,
)
from tests.test_data_source_migration import _database_url, temporary_database

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "checkpoint3_local_source"


@dataclass
class StaticImporter:
    loaded_items: list[NormalizedIngestionItem]
    source_type: str = "local_fixture"

    async def load_items(self) -> list[NormalizedIngestionItem]:
        return self.loaded_items


class CapturingCompletions:
    def __init__(self) -> None:
        self.request = None

    async def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Cedar Ridge is at risk."))]
        )


def _item(
    source_item_id: str,
    filename: str,
    content: bytes,
    source_modified_at: datetime | None = None,
) -> NormalizedIngestionItem:
    return NormalizedIngestionItem(
        source_item_id=source_item_id,
        filename=filename,
        content_type="text/plain",
        content=content,
        source_modified_at=source_modified_at or datetime(2026, 8, 12, tzinfo=UTC),
    )


def test_normalized_item_rejects_unsafe_or_missing_identity() -> None:
    with pytest.raises(ValueError, match="safe basename"):
        _item("item-1", "../outside.txt", b"content")
    with pytest.raises(ValueError, match="cannot be empty"):
        _item(" ", "inside.txt", b"content")


def test_local_fixture_adapter_rejects_path_escape(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "fixture_key": "unsafe",
                "items": [
                    {
                        "source_item_id": "item-1",
                        "filename": "inside.txt",
                        "path": "../outside.txt",
                        "content_type": "text/plain",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    importer = LocalFixtureImporter(tmp_path)
    with pytest.raises(ValueError, match="inside its fixture root"):
        asyncio.run(importer.load_items())


def test_checkpoint_three_fixture_emits_stable_normalized_items() -> None:
    importer = LocalFixtureImporter(FIXTURE_ROOT)
    items = asyncio.run(importer.load_items())

    assert importer.manifest.fixture_key == "checkpoint3-customer-renewal-v1"
    assert [item.source_item_id for item in items] == [
        "cedar-ridge/renewal-brief",
        "cedar-ridge/support-summary",
    ]
    assert [item.filename for item in items] == [
        "Cedar Ridge Renewal Brief.txt",
        "Cedar Ridge Support Summary.txt",
    ]
    assert all(item.content for item in items)


def test_repeated_import_preserves_provenance_uuid_and_workspace_scope(monkeypatch) -> None:
    with temporary_database() as (database, config):
        command.upgrade(config, "head")
        engine = create_async_engine(_database_url(database))
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        workspace_a = uuid.uuid4()
        workspace_b = uuid.uuid4()
        uploads: list[str] = []
        deleted: list[str] = []
        processor_calls: list[str] = []

        def upload(content: bytes, storage_key: str, _content_type: str) -> str:
            uploads.append(storage_key)
            assert content
            return storage_key

        def delete(storage_key: str) -> None:
            deleted.append(storage_key)

        async def processor(content: bytes, filename: str) -> dict:
            processor_calls.append(filename)
            return {
                "chunks": [content.decode()],
                "embeddings": [[1.0] + [0.0] * 1535],
            }

        first_items = [
            _item("renewal", "Renewal.txt", b"Cedar Ridge needs corrected adoption reporting."),
            _item("support", "Support.txt", b"Cedar Ridge has unresolved export failures."),
        ]

        async def exercise() -> None:
            async with session_factory() as db:
                db.add_all(
                    [
                        Workspace(
                            id=workspace_a,
                            name="Workspace A",
                            owner_subject="local-dev",
                            is_demo=False,
                        ),
                        Workspace(
                            id=workspace_b,
                            name="Workspace B",
                            owner_subject="local-dev",
                            is_demo=False,
                        ),
                    ]
                )
                await db.commit()
                source = await ensure_local_fixture_source(
                    db,
                    workspace_id=workspace_a,
                    owner_subject="local-dev",
                    fixture_key="checkpoint3-test",
                    name="Checkpoint 3 Local Fixture",
                )
                first = await import_from_source(
                    db=db,
                    workspace_id=workspace_a,
                    data_source_id=source.id,
                    importer=StaticImporter(first_items),
                    upload=upload,
                    delete=lambda _key: None,
                    processor=processor,
                )
                assert (first.created, first.updated, first.unchanged) == (2, 0, 0)
                original_ids = set(
                    (
                        await db.execute(
                            select(Document.id).where(Document.workspace_id == workspace_a)
                        )
                    ).scalars()
                )

                same_content_with_newer_timestamp = [
                    _item(
                        item.source_item_id or "",
                        item.filename,
                        item.content,
                        datetime(2026, 8, 20, tzinfo=UTC),
                    )
                    for item in first_items
                ]
                second = await import_from_source(
                    db=db,
                    workspace_id=workspace_a,
                    data_source_id=source.id,
                    importer=StaticImporter(same_content_with_newer_timestamp),
                    upload=upload,
                    delete=lambda _key: None,
                    processor=processor,
                )
                assert (second.created, second.updated, second.unchanged) == (0, 0, 2)
                assert len(uploads) == 2
                assert len(processor_calls) == 2
                synced_documents = list(
                    (
                        await db.execute(
                            select(Document).where(Document.workspace_id == workspace_a)
                        )
                    ).scalars()
                )
                assert all(
                    document.source_modified_at == datetime(2026, 8, 20, tzinfo=UTC)
                    for document in synced_documents
                )

                changed_items = [
                    _item(
                        "renewal",
                        "Renewal.txt",
                        b"Cedar Ridge needs a corrected regional adoption report before renewal.",
                    ),
                    first_items[1],
                ]
                changed = await import_from_source(
                    db=db,
                    workspace_id=workspace_a,
                    data_source_id=source.id,
                    importer=StaticImporter(changed_items),
                    upload=upload,
                    delete=delete,
                    processor=processor,
                )
                assert (changed.created, changed.updated, changed.unchanged) == (0, 1, 1)
                current_documents = list(
                    (
                        await db.execute(
                            select(Document).where(Document.workspace_id == workspace_a)
                        )
                    ).scalars()
                )
                assert {document.id for document in current_documents} == original_ids
                assert len(current_documents) == 2
                assert all(document.data_source_id == source.id for document in current_documents)
                assert all(document.source_item_id for document in current_documents)
                assert all(document.source_synced_at for document in current_documents)
                assert all(document.content_sha256 for document in current_documents)
                assert uploads[2] not in uploads[:2]
                assert deleted == [uploads[0]]
                assert await db.scalar(
                    select(func.count(DocumentChunk.id)).where(
                        DocumentChunk.workspace_id == workspace_a
                    )
                ) == 2

                with pytest.raises(ValueError, match="not available"):
                    await import_from_source(
                        db=db,
                        workspace_id=workspace_b,
                        data_source_id=source.id,
                        importer=StaticImporter(first_items),
                        upload=upload,
                        delete=lambda _key: None,
                        processor=processor,
                    )
                assert await db.scalar(
                    select(func.count(Document.id)).where(Document.workspace_id == workspace_b)
                ) == 0

                source_b = await ensure_local_fixture_source(
                    db,
                    workspace_id=workspace_b,
                    owner_subject="local-dev",
                    fixture_key="checkpoint3-test",
                    name="Checkpoint 3 Local Fixture",
                )
                await import_from_source(
                    db=db,
                    workspace_id=workspace_b,
                    data_source_id=source_b.id,
                    importer=StaticImporter(
                        [_item("renewal", "Private.txt", b"Workspace B private fact.")]
                    ),
                    upload=upload,
                    delete=lambda _key: None,
                    processor=processor,
                )
                assert await db.scalar(
                    select(func.count(Document.id)).where(Document.workspace_id == workspace_b)
                ) == 1

                completions = CapturingCompletions()

                async def query_embedding(_query: str) -> list[float]:
                    return [1.0] + [0.0] * 1535

                monkeypatch.setattr(search_service, "generate_embedding", query_embedding)
                monkeypatch.setattr(
                    rag_service,
                    "get_openai_client",
                    lambda: SimpleNamespace(chat=SimpleNamespace(completions=completions)),
                )
                answer = await rag_service.answer_question(
                    db,
                    workspace_a,
                    "What is blocking the Cedar Ridge renewal?",
                )
                assert {source["filename"] for source in answer["sources"]} == {
                    "Renewal.txt",
                    "Support.txt",
                }
                prompt = completions.request["messages"][1]["content"]
                assert "corrected regional adoption report" in prompt
                assert "unresolved export failures" in prompt
                assert "Workspace B private fact" not in prompt

            await engine.dispose()

        asyncio.run(exercise())


def test_failed_update_keeps_storage_and_database_on_the_same_version(monkeypatch) -> None:
    with temporary_database() as (database, config):
        command.upgrade(config, "head")
        engine = create_async_engine(_database_url(database))
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        workspace_id = uuid.uuid4()
        stored: dict[str, bytes] = {}

        def upload(content: bytes, storage_key: str, _content_type: str) -> str:
            stored[storage_key] = content
            return storage_key

        def delete(storage_key: str) -> None:
            stored.pop(storage_key, None)

        async def processor(content: bytes, _filename: str) -> dict:
            return {"chunks": [content.decode()], "embeddings": [[1.0] + [0.0] * 1535]}

        original = b"Original renewal brief."

        async def exercise() -> None:
            async with session_factory() as db:
                db.add(
                    Workspace(
                        id=workspace_id,
                        name="Workspace",
                        owner_subject="local-dev",
                        is_demo=False,
                    )
                )
                await db.commit()
                source = await ensure_local_fixture_source(
                    db,
                    workspace_id=workspace_id,
                    owner_subject="local-dev",
                    fixture_key="checkpoint3-failure",
                    name="Failure fixture",
                )
                await import_from_source(
                    db=db,
                    workspace_id=workspace_id,
                    data_source_id=source.id,
                    importer=StaticImporter([_item("brief", "Brief.txt", original)]),
                    upload=upload,
                    delete=delete,
                    processor=processor,
                )
                before = (await db.execute(select(Document))).scalar_one()
                key_before, sha_before = before.storage_key, before.content_sha256

                async def failing_save_chunks(**_kwargs) -> None:
                    raise RuntimeError("database write failed")

                monkeypatch.setattr(document_ingestion, "save_chunks", failing_save_chunks)
                with pytest.raises(RuntimeError, match="database write failed"):
                    await import_from_source(
                        db=db,
                        workspace_id=workspace_id,
                        data_source_id=source.id,
                        importer=StaticImporter([_item("brief", "Brief.txt", b"Changed brief.")]),
                        upload=upload,
                        delete=delete,
                        processor=processor,
                    )

                db.expire_all()
                after = (await db.execute(select(Document))).scalar_one()
                assert after.storage_key == key_before
                assert after.content_sha256 == sha_before
                assert stored == {key_before: original}
                chunks = list((await db.execute(select(DocumentChunk.content))).scalars())
                assert chunks == [original.decode()]

            await engine.dispose()

        asyncio.run(exercise())


def test_import_failure_persists_scoped_source_error() -> None:
    with temporary_database() as (database, config):
        command.upgrade(config, "head")
        engine = create_async_engine(_database_url(database))
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        workspace_id = uuid.uuid4()

        async def exercise() -> None:
            async with session_factory() as db:
                with pytest.raises(ValueError, match="Private workspace"):
                    await ensure_local_fixture_source(
                        db,
                        workspace_id=DEMO_WORKSPACE_ID,
                        owner_subject="local-dev",
                        fixture_key="forbidden-demo",
                        name="Forbidden",
                    )
                db.add(
                    Workspace(
                        id=workspace_id,
                        name="Workspace",
                        owner_subject="local-dev",
                        is_demo=False,
                    )
                )
                await db.commit()
                source = await ensure_local_fixture_source(
                    db,
                    workspace_id=workspace_id,
                    owner_subject="local-dev",
                    fixture_key="failure-test",
                    name="Failure Fixture",
                )
                source_id = source.id

                async def failing_processor(_content: bytes, _filename: str) -> dict:
                    raise ValueError("processing failed")

                with pytest.raises(ValueError, match="processing failed"):
                    await import_from_source(
                        db=db,
                        workspace_id=workspace_id,
                        data_source_id=source_id,
                        importer=StaticImporter([_item("item", "Item.txt", b"content")]),
                        upload=lambda _content, key, _content_type: key,
                        delete=lambda _key: None,
                        processor=failing_processor,
                    )
                refreshed = await db.get(DataSource, source_id)
                assert refreshed is not None
                assert refreshed.workspace_id == workspace_id
                assert refreshed.status == "error"
                assert refreshed.error == "The most recent source import failed."

            await engine.dispose()

        asyncio.run(exercise())
