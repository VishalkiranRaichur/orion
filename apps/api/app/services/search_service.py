from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Document
from app.models.document_chunk import DocumentChunk
from app.services.embedding_service import generate_embedding


async def semantic_search(
    db: AsyncSession,
    workspace_id: UUID,
    query: str,
    limit: int = 5,
    document_ids: list[UUID] | None = None,
) -> list[DocumentChunk]:
    query_embedding = await generate_embedding(query)

    if document_ids:
        accessible_ids = set(
            (
                await db.execute(
                    select(Document.id).where(
                        Document.workspace_id == workspace_id,
                        Document.id.in_(document_ids),
                    )
                )
            ).scalars()
        )
        if accessible_ids != set(document_ids):
            raise ValueError("One or more documents are not available in this workspace.")

    statement = (
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .options(joinedload(DocumentChunk.document))
        .where(
            DocumentChunk.workspace_id == workspace_id,
            Document.workspace_id == workspace_id,
            Document.status == "processed",
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
    )
    if document_ids:
        statement = statement.where(DocumentChunk.document_id.in_(document_ids))
    statement = statement.limit(limit)

    result = await db.execute(statement)

    return list(result.scalars().all())
