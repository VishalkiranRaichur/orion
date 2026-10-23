import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

import app.routers.ask as ask_router
import app.routers.documents as documents_router
from app.db import get_db
from app.main import app
from app.models import Workspace
from app.workspaces import get_active_workspace, get_mutable_workspace

WORKSPACE_ID = uuid.uuid4()
WORKSPACE = Workspace(
    id=WORKSPACE_ID,
    name="Test Company",
    owner_subject="local-dev",
    is_demo=False,
)


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.committed = False
        self.rolled_back = False

    def add(self, value) -> None:
        self.added.append(value)

    def add_all(self, values) -> None:
        self.added.extend(values)

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, value) -> None:
        if value.created_at is None:
            value.created_at = datetime.now(UTC)


def override_database(session: FakeSession):
    async def _override():
        yield session

    return _override


async def override_workspace() -> Workspace:
    return WORKSPACE


def test_ask_returns_grounded_answer(monkeypatch) -> None:
    session = FakeSession()

    async def fake_answer_question(**_kwargs):
        return {
            "answer": "The contract renews annually.",
            "sources": [
                {
                    "chunk_id": "chunk-1",
                    "document_id": "document-1",
                    "filename": "contract.txt",
                    "chunk_index": 0,
                    "content": "The contract renews annually.",
                }
            ],
        }

    monkeypatch.setattr(ask_router, "answer_question", fake_answer_question)
    app.dependency_overrides[get_db] = override_database(session)
    app.dependency_overrides[get_active_workspace] = override_workspace

    try:
        response = TestClient(app).post(
            "/api/v1/ask",
            json={"question": "When does the contract renew?", "limit": 5},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["sources"][0]["filename"] == "contract.txt"


def test_upload_stores_and_processes_document(monkeypatch) -> None:
    session = FakeSession()

    def fake_upload_file(*_args) -> str:
        return "documents/id/notes.txt"

    async def fake_process_document(_file_bytes: bytes, _filename: str):
        return {
            "chunks": ["A useful source passage."],
            "embeddings": [[0.0] * 1536],
        }

    monkeypatch.setattr(documents_router, "upload_file", fake_upload_file)
    monkeypatch.setattr(documents_router, "process_document", fake_process_document)
    app.dependency_overrides[get_db] = override_database(session)
    app.dependency_overrides[get_mutable_workspace] = override_workspace

    try:
        response = TestClient(app).post(
            "/api/v1/documents/upload",
            files={"file": ("notes.txt", b"A useful source passage.", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["filename"] == "notes.txt"
    assert response.json()["status"] == "processed"
    assert response.json()["data_source_id"] is None
    assert response.json()["source_item_id"] is None
    assert response.json()["source_synced_at"] is None
    assert response.json()["storage_key"].startswith(f"workspaces/{WORKSPACE_ID}/documents/")
    assert session.committed is True


def test_upload_reports_storage_outage(monkeypatch) -> None:
    session = FakeSession()

    def unavailable_storage(*_args):
        raise ConnectionError("MinIO refused the connection")

    monkeypatch.setattr(documents_router, "upload_file", unavailable_storage)
    app.dependency_overrides[get_db] = override_database(session)
    app.dependency_overrides[get_mutable_workspace] = override_workspace

    try:
        response = TestClient(app).post(
            "/api/v1/documents/upload",
            files={"file": ("notes.txt", b"Some content", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Document storage is unavailable. Check the MinIO service."
    )
    assert session.rolled_back is True
