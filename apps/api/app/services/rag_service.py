import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.openai_client import get_openai_client
from app.services.search_service import semantic_search


async def answer_question(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    question: str,
    limit: int = 5,
) -> dict:
    cleaned_question = question.strip()

    if not cleaned_question:
        raise ValueError("Question cannot be empty.")

    chunks = await semantic_search(
        db=db,
        workspace_id=workspace_id,
        query=cleaned_question,
        limit=limit,
    )

    if not chunks:
        return {
            "answer": "I could not find relevant information in the uploaded documents.",
            "sources": [],
        }

    context = "\n\n---\n\n".join(
        f"SOURCE {index}: {chunk.document.filename}\n{chunk.content}"
        for index, chunk in enumerate(chunks, start=1)
    )

    client = get_openai_client()

    response = await client.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are Admin AI. Answer using only the retrieved document context. Give the "
                    "strongest answer directly supported by responsive facts in that context. "
                    "Clearly distinguish observed facts from likely explanations or inferences, "
                    "and state uncertainty when the documents do not prove causation. A partial, "
                    "qualified answer is preferable to a refusal. Refuse only when the context "
                    "contains no facts responsive to the question. Do not invent facts."
                ),
            },
            {
                "role": "user",
                "content": f"DOCUMENT CONTEXT:\n{context}\n\nUSER QUESTION:\n{cleaned_question}",
            },
        ],
        temperature=0,
    )

    answer = response.choices[0].message.content or ""

    return {
        "answer": answer,
        "sources": [
            {
                "chunk_id": str(chunk.id),
                "document_id": str(chunk.document_id),
                "filename": chunk.document.filename,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
            }
            for chunk in chunks
        ],
    }
