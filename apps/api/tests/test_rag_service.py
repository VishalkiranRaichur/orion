import uuid
from types import SimpleNamespace

import pytest

import app.services.rag_service as rag_service


def _chunk(filename: str, content: str, index: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document=SimpleNamespace(filename=filename),
        chunk_index=index,
        content=content,
    )


class CapturingCompletions:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.request = None

    async def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.answer))]
        )


@pytest.mark.asyncio
async def test_grounded_synthesis_receives_ordered_chunks_and_preserves_sources(
    monkeypatch,
) -> None:
    workspace_id = uuid.uuid4()
    chunks = [
        _chunk("first.md", "First retrieved fact."),
        _chunk("second.md", "Second retrieved fact.", index=2),
    ]
    search_call = {}
    completions = CapturingCompletions("A qualified answer.")

    async def fake_search(**kwargs):
        search_call.update(kwargs)
        return chunks

    monkeypatch.setattr(rag_service, "semantic_search", fake_search)
    monkeypatch.setattr(
        rag_service,
        "get_openai_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    result = await rag_service.answer_question(
        db=object(),
        workspace_id=workspace_id,
        question="What happened?",
        limit=5,
    )

    assert search_call["workspace_id"] == workspace_id
    assert search_call["query"] == "What happened?"
    user_context = completions.request["messages"][1]["content"]
    assert user_context.index(chunks[0].content) < user_context.index(chunks[1].content)
    assert chunks[0].content in user_context
    assert chunks[1].content in user_context
    system_prompt = completions.request["messages"][0]["content"]
    assert "strongest answer directly supported" in system_prompt
    assert "likely explanations or inferences" in system_prompt
    assert "state uncertainty" in system_prompt
    assert "Refuse only when" in system_prompt
    assert result["sources"] == [
        {
            "chunk_id": str(chunk.id),
            "document_id": str(chunk.document_id),
            "filename": chunk.document.filename,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
        }
        for chunk in chunks
    ]


@pytest.mark.asyncio
async def test_demo_grounded_answer_contract_includes_facts_inference_and_uncertainty(
    monkeypatch,
) -> None:
    chunks = [
        _chunk(
            "northstar_2026.md",
            "Northstar monthly recognized revenue fell from $120,000 to $40,000.",
        ),
        _chunk(
            "northstar_renewal.md",
            "Northstar requested narrower scope while export reliability remained unresolved.",
        ),
    ]
    answer = (
        "Northstar monthly recognized revenue fell from $120,000 to $40,000, an approximately "
        "$80,000 decline. The documents suggest the narrower renewal was related to unresolved "
        "export reliability, but they do not establish a definitive company-wide causal conclusion."
    )
    completions = CapturingCompletions(answer)

    async def fake_search(**_kwargs):
        return chunks

    monkeypatch.setattr(rag_service, "semantic_search", fake_search)
    monkeypatch.setattr(
        rag_service,
        "get_openai_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    result = await rag_service.answer_question(
        db=object(),
        workspace_id=uuid.uuid4(),
        question="Why did revenue decline in July?",
    )

    normalized = result["answer"].lower()
    assert "$120,000" in result["answer"]
    assert "$40,000" in result["answer"]
    assert "$80,000" in result["answer"]
    assert "export reliability" in normalized
    assert "do not establish" in normalized
    assert "company-wide causal conclusion" in normalized
