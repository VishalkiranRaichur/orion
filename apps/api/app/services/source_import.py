from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_sources import find_workspace_data_source
from app.models import DataSource, Document
from app.services.document_ingestion import (
    DeleteAdapter,
    ProcessorAdapter,
    UploadAdapter,
    ingest_document,
    replace_document_content,
)

DOCUMENT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "orion:source-document")
ImportAction = Literal["created", "updated", "unchanged"]


@dataclass(frozen=True)
class NormalizedIngestionItem:
    filename: str
    content_type: str
    content: bytes
    source_item_id: str | None = None
    source_modified_at: datetime | None = None

    def __post_init__(self) -> None:
        filename = self.filename.strip()
        if not filename or Path(filename).name != filename:
            raise ValueError("Ingestion item filename must be a safe basename.")
        if not self.content_type.strip():
            raise ValueError("Ingestion item content type cannot be empty.")
        if not self.content:
            raise ValueError("Ingestion item content cannot be empty.")
        if self.source_item_id is not None:
            source_item_id = self.source_item_id.strip()
            if not source_item_id:
                raise ValueError("Source item ID cannot be empty.")
            if len(source_item_id) > 500:
                raise ValueError("Source item ID cannot exceed 500 characters.")
            object.__setattr__(self, "source_item_id", source_item_id)
        object.__setattr__(self, "filename", filename)
        object.__setattr__(self, "content_type", self.content_type.strip())


class SourceImporter(Protocol):
    source_type: str

    async def load_items(self) -> list[NormalizedIngestionItem]: ...


@dataclass(frozen=True)
class ImportOutcome:
    document: Document
    action: ImportAction


@dataclass(frozen=True)
class ImportSummary:
    source_id: uuid.UUID
    created: int
    updated: int
    unchanged: int


def source_document_id(
    workspace_id: uuid.UUID,
    data_source_id: uuid.UUID,
    source_item_id: str,
) -> uuid.UUID:
    return uuid.uuid5(
        DOCUMENT_NAMESPACE,
        f"{workspace_id}:{data_source_id}:{source_item_id}",
    )


async def ingest_normalized_item(
    *,
    db: AsyncSession,
    workspace_id: uuid.UUID,
    item: NormalizedIngestionItem,
    upload: UploadAdapter,
    delete: DeleteAdapter,
    processor: ProcessorAdapter,
    data_source: DataSource | None = None,
    document_id: uuid.UUID | None = None,
) -> ImportOutcome:
    if data_source is not None and data_source.workspace_id != workspace_id:
        raise ValueError("Data source is not available in this workspace.")
    if item.source_item_id is not None and data_source is None:
        raise ValueError("Source item provenance requires a data source.")

    content_sha256 = hashlib.sha256(item.content).hexdigest()
    synced_at = datetime.now(UTC) if data_source is not None else None
    existing = None
    if data_source is not None and item.source_item_id is not None:
        existing = (
            await db.execute(
                select(Document).where(
                    Document.workspace_id == workspace_id,
                    Document.data_source_id == data_source.id,
                    Document.source_item_id == item.source_item_id,
                )
            )
        ).scalar_one_or_none()

    if existing is not None and existing.content_sha256 == content_sha256:
        existing.source_modified_at = item.source_modified_at
        existing.source_synced_at = synced_at
        await db.commit()
        await db.refresh(existing)
        return ImportOutcome(document=existing, action="unchanged")

    if existing is not None:
        document = await replace_document_content(
            db=db,
            document=existing,
            workspace_id=workspace_id,
            file_bytes=item.content,
            filename=item.filename,
            content_type=item.content_type,
            upload=upload,
            delete=delete,
            processor=processor,
            source_modified_at=item.source_modified_at,
            source_synced_at=synced_at,
            content_sha256=content_sha256,
        )
        return ImportOutcome(document=document, action="updated")

    if document_id is None and data_source is not None and item.source_item_id is not None:
        document_id = source_document_id(workspace_id, data_source.id, item.source_item_id)
    document_id = document_id or uuid.uuid4()
    storage_key = f"workspaces/{workspace_id}/documents/{document_id}/{item.filename}"
    document = await ingest_document(
        db=db,
        workspace_id=workspace_id,
        file_bytes=item.content,
        filename=item.filename,
        content_type=item.content_type,
        storage_key=storage_key,
        upload=upload,
        delete=delete,
        processor=processor,
        document_id=document_id,
        data_source_id=data_source.id if data_source is not None else None,
        source_item_id=item.source_item_id,
        source_modified_at=item.source_modified_at,
        source_synced_at=synced_at,
        content_sha256=content_sha256,
    )
    return ImportOutcome(document=document, action="created")


async def import_from_source(
    *,
    db: AsyncSession,
    workspace_id: uuid.UUID,
    data_source_id: uuid.UUID,
    importer: SourceImporter,
    upload: UploadAdapter,
    delete: DeleteAdapter,
    processor: ProcessorAdapter,
) -> ImportSummary:
    source = await find_workspace_data_source(db, workspace_id, data_source_id)
    if source is None:
        raise ValueError("Data source is not available in this workspace.")
    if source.source_type != importer.source_type:
        raise ValueError("Data source type does not match the importer.")

    try:
        items = await importer.load_items()
        source_item_ids = [item.source_item_id for item in items]
        if any(source_item_id is None for source_item_id in source_item_ids):
            raise ValueError("Source importers must provide a source item ID.")
        if len(source_item_ids) != len(set(source_item_ids)):
            raise ValueError("Source importer returned duplicate source item IDs.")

        counts: dict[ImportAction, int] = {"created": 0, "updated": 0, "unchanged": 0}
        for item in items:
            outcome = await ingest_normalized_item(
                db=db,
                workspace_id=workspace_id,
                item=item,
                upload=upload,
                delete=delete,
                processor=processor,
                data_source=source,
            )
            counts[outcome.action] += 1
        source.status = "ready"
        source.error = None
        source.last_synced_at = datetime.now(UTC)
        await db.commit()
        return ImportSummary(source_id=source.id, **counts)
    except Exception:
        await db.rollback()
        await db.execute(
            update(DataSource)
            .where(
                DataSource.id == data_source_id,
                DataSource.workspace_id == workspace_id,
            )
            .values(
                status="error",
                error="The most recent source import failed.",
                updated_at=datetime.now(UTC),
            )
        )
        await db.commit()
        raise
