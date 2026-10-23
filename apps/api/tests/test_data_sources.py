import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

import app.routers.documents as documents_router
from app.db import get_db
from app.main import app
from app.models import DEMO_WORKSPACE_ID, DataSource, Document, Workspace
from app.routers.data_sources import create_data_source, get_data_source, list_data_sources
from app.schemas.data_source import DataSourceCreate
from app.workspaces import get_active_workspace, get_mutable_workspace


class Result:
    def __init__(self, values: list) -> None:
        self.values = values

    def scalars(self) -> "Result":
        return self

    def all(self) -> list:
        return self.values

    def scalar_one_or_none(self):
        return self.values[0] if self.values else None


class FakeSession:
    def __init__(self, results: list[list] | None = None) -> None:
        self.results = list(results or [])
        self.statements = []
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement) -> Result:
        self.statements.append(statement)
        return Result(self.results.pop(0) if self.results else [])

    def add(self, value) -> None:
        self.added.append(value)

    def add_all(self, values) -> None:
        self.added.extend(values)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, value) -> None:
        now = datetime.now(UTC)
        value.created_at = value.created_at or now
        if hasattr(value, "updated_at"):
            value.updated_at = value.updated_at or now


def _sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _workspace(*, demo: bool = False) -> Workspace:
    return Workspace(
        id=DEMO_WORKSPACE_ID if demo else uuid.uuid4(),
        name="Demo" if demo else "Private",
        owner_subject=None if demo else "user-a",
        is_demo=demo,
    )


def _source(workspace_id: uuid.UUID) -> DataSource:
    now = datetime.now(UTC)
    return DataSource(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        name="Contracts",
        source_type="upload",
        status="ready",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_data_source_listing_and_detail_are_workspace_scoped() -> None:
    workspace = _workspace()
    source = _source(workspace.id)
    session = FakeSession([[source], []])

    assert await list_data_sources(workspace=workspace, db=session) == [source]
    listing_sql = _sql(session.statements[0])
    assert f"data_sources.workspace_id = '{workspace.id}'" in listing_sql

    with pytest.raises(HTTPException) as raised:
        await get_data_source(data_source_id=uuid.uuid4(), workspace=workspace, db=session)
    assert raised.value.status_code == 404
    assert f"data_sources.workspace_id = '{workspace.id}'" in _sql(session.statements[1])


@pytest.mark.asyncio
async def test_create_data_source_trims_name_and_sets_server_managed_fields() -> None:
    workspace = _workspace()
    session = FakeSession()

    source = await create_data_source(
        request=DataSourceCreate(name="  Customer Contracts  "),
        workspace=workspace,
        db=session,
    )

    assert source.workspace_id == workspace.id
    assert source.name == "Customer Contracts"
    assert source.source_type == "upload"
    assert source.status == "ready"
    assert source.external_key is None
    assert session.commits == 1


@pytest.mark.asyncio
async def test_source_filtered_document_listing_keeps_workspace_predicate(
    monkeypatch,
) -> None:
    workspace = _workspace()
    source = _source(workspace.id)
    session = FakeSession([[]])

    async def resolve_source(*_args):
        return source

    monkeypatch.setattr(documents_router, "find_workspace_data_source", resolve_source)
    assert await documents_router.list_documents(
        data_source_id=source.id,
        workspace=workspace,
        db=session,
    ) == []
    statement = _sql(session.statements[0])
    assert f"documents.workspace_id = '{workspace.id}'" in statement
    assert f"documents.data_source_id = '{source.id}'" in statement


def test_demo_workspace_rejects_data_source_creation() -> None:
    demo = _workspace(demo=True)

    async def override_demo() -> Workspace:
        return demo

    async def unused_database():
        raise AssertionError("Database should not be used for a rejected demo mutation")
        yield

    app.dependency_overrides[get_active_workspace] = override_demo
    app.dependency_overrides[get_db] = unused_database
    try:
        response = TestClient(app).post(
            "/api/v1/data-sources",
            headers={"X-Workspace-ID": str(DEMO_WORKSPACE_ID)},
            json={"name": "Forbidden", "source_type": "upload"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "The demo workspace is read-only."


def test_source_targeted_upload_persists_association(monkeypatch) -> None:
    workspace = _workspace()
    source = _source(workspace.id)
    session = FakeSession()

    async def resolve_source(*_args):
        return source

    async def process(_file_bytes: bytes, _filename: str):
        return {"chunks": ["A contract fact."], "embeddings": [[0.0] * 1536]}

    async def override_workspace() -> Workspace:
        return workspace

    async def override_database():
        yield session

    monkeypatch.setattr(documents_router, "find_workspace_data_source", resolve_source)
    monkeypatch.setattr(documents_router, "process_document", process)
    monkeypatch.setattr(documents_router, "upload_file", lambda *_args: "stored")
    app.dependency_overrides[get_mutable_workspace] = override_workspace
    app.dependency_overrides[get_db] = override_database
    try:
        response = TestClient(app).post(
            "/api/v1/documents/upload",
            files={"file": ("contract.txt", b"A contract fact.", "text/plain")},
            data={"data_source_id": str(source.id)},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["data_source_id"] == str(source.id)
    document = next(value for value in session.added if isinstance(value, Document))
    assert document.workspace_id == workspace.id
    assert document.data_source_id == source.id
    assert source.last_synced_at is not None
    assert source.error is None


def test_cross_workspace_source_is_rejected_before_storage(monkeypatch) -> None:
    workspace = _workspace()
    session = FakeSession()
    storage_called = False

    async def missing_source(*_args):
        return None

    def unexpected_storage(*_args):
        nonlocal storage_called
        storage_called = True
        raise AssertionError("storage must not run")

    async def override_workspace() -> Workspace:
        return workspace

    async def override_database():
        yield session

    monkeypatch.setattr(documents_router, "find_workspace_data_source", missing_source)
    monkeypatch.setattr(documents_router, "upload_file", unexpected_storage)
    app.dependency_overrides[get_mutable_workspace] = override_workspace
    app.dependency_overrides[get_db] = override_database
    try:
        response = TestClient(app).post(
            "/api/v1/documents/upload",
            files={"file": ("contract.txt", b"A contract fact.", "text/plain")},
            data={"data_source_id": str(uuid.uuid4())},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Data source not found."
    assert storage_called is False


def test_local_fixture_source_rejects_manual_upload(monkeypatch) -> None:
    workspace = _workspace()
    source = _source(workspace.id)
    source.source_type = "local_fixture"
    session = FakeSession()
    storage_called = False

    async def resolve_source(*_args):
        return source

    def unexpected_storage(*_args):
        nonlocal storage_called
        storage_called = True
        raise AssertionError("storage must not run")

    async def override_workspace() -> Workspace:
        return workspace

    async def override_database():
        yield session

    monkeypatch.setattr(documents_router, "find_workspace_data_source", resolve_source)
    monkeypatch.setattr(documents_router, "upload_file", unexpected_storage)
    app.dependency_overrides[get_mutable_workspace] = override_workspace
    app.dependency_overrides[get_db] = override_database
    try:
        response = TestClient(app).post(
            "/api/v1/documents/upload",
            files={"file": ("contract.txt", b"A contract fact.", "text/plain")},
            data={"data_source_id": str(source.id)},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "This data source does not accept manual uploads."
    assert storage_called is False


def test_source_import_failure_is_scoped_and_persisted(monkeypatch) -> None:
    workspace = _workspace()
    source = _source(workspace.id)
    session = FakeSession()

    async def resolve_source(*_args):
        return source

    async def override_workspace() -> Workspace:
        return workspace

    async def override_database():
        yield session

    def unavailable_storage(*_args):
        raise ConnectionError("unavailable")

    monkeypatch.setattr(documents_router, "find_workspace_data_source", resolve_source)
    monkeypatch.setattr(documents_router, "upload_file", unavailable_storage)
    app.dependency_overrides[get_mutable_workspace] = override_workspace
    app.dependency_overrides[get_db] = override_database
    try:
        response = TestClient(app).post(
            "/api/v1/documents/upload",
            files={"file": ("contract.txt", b"A contract fact.", "text/plain")},
            data={"data_source_id": str(source.id)},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert session.rollbacks >= 1
    assert session.commits == 1
    failure_statement = _sql(session.statements[-1])
    assert f"data_sources.id = '{source.id}'" in failure_statement
    assert f"data_sources.workspace_id = '{workspace.id}'" in failure_statement
