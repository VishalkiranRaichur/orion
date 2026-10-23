import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from openai import OpenAIError
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.data_sources import find_workspace_data_source
from app.db import get_db
from app.models import DataSource, Document, Workspace
from app.schemas import DocumentResponse
from app.services.document_processor import process_document
from app.services.embedding_service import OpenAIConfigurationError
from app.services.source_import import NormalizedIngestionItem, ingest_normalized_item
from app.services.storage import delete_file, upload_file
from app.workspaces import get_active_workspace, get_mutable_workspace

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".md"}


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    data_source_id: uuid.UUID | None = None,
    workspace: Workspace = Depends(get_active_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[Document]:
    try:
        statement = select(Document).where(Document.workspace_id == workspace.id)
        if data_source_id is not None:
            data_source = await find_workspace_data_source(db, workspace.id, data_source_id)
            if data_source is None:
                raise HTTPException(status_code=404, detail="Data source not found.")
            statement = statement.where(Document.data_source_id == data_source.id)
        result = await db.execute(statement.order_by(Document.created_at.desc()))
        return list(result.scalars().all())
    except SQLAlchemyError as error:
        logger.exception("Failed to list documents")
        raise HTTPException(
            status_code=503,
            detail="The document database is unavailable.",
        ) from error


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=201,
)
async def upload_document(
    file: UploadFile = File(...),
    data_source_id: uuid.UUID | None = Form(default=None),
    workspace: Workspace = Depends(get_mutable_workspace),
    db: AsyncSession = Depends(get_db),
) -> Document:
    data_source = None
    if data_source_id is not None:
        data_source = await find_workspace_data_source(db, workspace.id, data_source_id)
        if data_source is None:
            raise HTTPException(status_code=404, detail="Data source not found.")
        if data_source.source_type != "upload":
            raise HTTPException(
                status_code=400,
                detail="This data source does not accept manual uploads.",
            )

    filename = Path(file.filename or "unnamed").name

    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type.",
        )

    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty.",
        )

    max_size_bytes = settings.max_upload_size_mb * 1024 * 1024

    if len(file_bytes) > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_upload_size_mb} MB upload limit.",
        )

    document_id = uuid.uuid4()

    content_type = file.content_type or "application/octet-stream"

    try:
        if data_source is not None:
            data_source.status = "ready"
            data_source.error = None
            data_source.last_synced_at = datetime.now(UTC)
        outcome = await ingest_normalized_item(
            db=db,
            workspace_id=workspace.id,
            item=NormalizedIngestionItem(
                filename=filename,
                content_type=content_type,
                content=file_bytes,
            ),
            upload=upload_file,
            delete=delete_file,
            processor=process_document,
            document_id=document_id,
            data_source=data_source,
        )
        document = outcome.document

    except (OpenAIConfigurationError, OpenAIError, SQLAlchemyError, ValueError) as error:
        await _record_source_failure(db, workspace.id, data_source_id)
        logger.exception("Document processing failed for %s", filename)

        status_code = 502 if isinstance(error, OpenAIError) else 422
        if isinstance(error, OpenAIConfigurationError):
            status_code = 503
        if isinstance(error, SQLAlchemyError):
            status_code = 503

        raise HTTPException(
            status_code=status_code,
            detail=f"Document processing failed: {error}",
        ) from error
    except Exception as error:
        await _record_source_failure(db, workspace.id, data_source_id)
        logger.exception("Document upload failed for %s", filename)
        raise HTTPException(
            status_code=503,
            detail="Document storage is unavailable. Check the MinIO service.",
        ) from error

    return document


async def _record_source_failure(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    data_source_id: uuid.UUID | None,
) -> None:
    if data_source_id is None:
        return
    try:
        await db.execute(
            update(DataSource)
            .where(
                DataSource.id == data_source_id,
                DataSource.workspace_id == workspace_id,
            )
            .values(
                status="error",
                error="The most recent document import failed.",
                updated_at=datetime.now(UTC),
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Could not persist data source import failure")
