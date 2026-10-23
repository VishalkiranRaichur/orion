from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy import delete as delete_statement
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk
from app.services.chunk_repository import save_chunks

UploadAdapter = Callable[[bytes, str, str], str]
DeleteAdapter = Callable[[str], None]
ProcessorAdapter = Callable[[bytes, str], Awaitable[dict]]

logger = logging.getLogger(__name__)


def versioned_storage_key(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    content_sha256: str,
    filename: str,
) -> str:
    """Return an object key that is unique per document content version."""
    return f"workspaces/{workspace_id}/documents/{document_id}/{content_sha256[:16]}/{filename}"


async def ingest_document(
    *,
    db: AsyncSession,
    workspace_id: uuid.UUID,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    storage_key: str,
    upload: UploadAdapter,
    delete: DeleteAdapter,
    processor: ProcessorAdapter,
    document_id: uuid.UUID | None = None,
    data_source_id: uuid.UUID | None = None,
    source_item_id: str | None = None,
    source_modified_at: datetime | None = None,
    source_synced_at: datetime | None = None,
    content_sha256: str | None = None,
    commit: bool = True,
) -> Document:
    """Store, parse, chunk, embed, and persist a document without HTTP concerns."""
    document = Document(
        id=document_id or uuid.uuid4(),
        workspace_id=workspace_id,
        data_source_id=data_source_id,
        source_item_id=source_item_id,
        source_modified_at=source_modified_at,
        source_synced_at=source_synced_at,
        content_sha256=content_sha256,
        filename=filename,
        content_type=content_type,
        size_bytes=len(file_bytes),
        storage_key=storage_key,
        status="uploaded",
    )
    storage_uploaded = False
    try:
        await asyncio.to_thread(upload, file_bytes, storage_key, content_type)
        storage_uploaded = True
        result = await processor(file_bytes, filename)
        db.add(document)
        await save_chunks(
            db=db,
            workspace_id=workspace_id,
            document_id=document.id,
            chunks=result["chunks"],
            embeddings=result["embeddings"],
        )
        document.status = "processed"
        if commit:
            await db.commit()
            await db.refresh(document)
        else:
            await db.flush()
        return document
    except Exception:
        await db.rollback()
        if storage_uploaded:
            try:
                await asyncio.to_thread(delete, storage_key)
            except Exception:
                logger.warning("Could not remove orphaned object %s", storage_key, exc_info=True)
        raise


async def replace_document_content(
    *,
    db: AsyncSession,
    document: Document,
    workspace_id: uuid.UUID,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    upload: UploadAdapter,
    delete: DeleteAdapter,
    processor: ProcessorAdapter,
    source_modified_at: datetime | None,
    source_synced_at: datetime,
    content_sha256: str,
) -> Document:
    """Reprocess an imported item while retaining its logical document UUID.

    The new content is written to a new, content-versioned object key and the
    database pointer moves to it inside the same transaction as the chunk swap.
    The previous object is removed only after the commit succeeds, so a failure
    at any step leaves the stored file and the database describing the same
    version.
    """
    if document.workspace_id != workspace_id:
        raise ValueError("Document is not available in this workspace.")

    result = await processor(file_bytes, filename)
    previous_key = document.storage_key
    new_key = versioned_storage_key(workspace_id, document.id, content_sha256, filename)
    await asyncio.to_thread(upload, file_bytes, new_key, content_type)
    try:
        await db.execute(
            delete_statement(DocumentChunk).where(
                DocumentChunk.workspace_id == workspace_id,
                DocumentChunk.document_id == document.id,
            )
        )
        document.filename = filename
        document.content_type = content_type
        document.size_bytes = len(file_bytes)
        document.storage_key = new_key
        document.source_modified_at = source_modified_at
        document.source_synced_at = source_synced_at
        document.content_sha256 = content_sha256
        document.status = "processed"
        await save_chunks(
            db=db,
            workspace_id=workspace_id,
            document_id=document.id,
            chunks=result["chunks"],
            embeddings=result["embeddings"],
        )
        await db.commit()
        await db.refresh(document)
    except Exception:
        await db.rollback()
        if new_key != previous_key:
            try:
                await asyncio.to_thread(delete, new_key)
            except Exception:
                logger.warning("Could not remove orphaned object %s", new_key, exc_info=True)
        raise

    if previous_key != new_key:
        try:
            await asyncio.to_thread(delete, previous_key)
        except Exception:
            logger.warning("Could not remove superseded object %s", previous_key, exc_info=True)
    return document
