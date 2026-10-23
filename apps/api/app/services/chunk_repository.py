from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_chunk import DocumentChunk


async def save_chunks(
    db: AsyncSession,
    workspace_id: UUID,
    document_id: UUID,
    chunks: list[str],
    embeddings: list[list[float]],
) -> list[DocumentChunk]:
    if len(chunks) != len(embeddings):
        raise ValueError("The number of chunks must match the number of embeddings.")

    chunk_objects = [
        DocumentChunk(
            workspace_id=workspace_id,
            document_id=document_id,
            chunk_index=index,
            content=chunk,
            embedding=embedding,
        )
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]

    db.add_all(chunk_objects)

    return chunk_objects
