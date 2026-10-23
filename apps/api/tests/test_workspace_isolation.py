import ast
import uuid
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

import app.investigations.tools as tools_module
import app.services.search_service as search_service
from app.investigations.budget import ExecutionBudget
from app.investigations.errors import RequiredDataError
from app.investigations.orchestrator import InvestigationOrchestrator
from app.investigations.tools import ToolExecutor
from app.main import app
from app.models import (
    DEMO_WORKSPACE_ID,
    BusinessRecord,
    Claim,
    DataSource,
    Document,
    DocumentChunk,
    Entity,
    EntityRelationship,
    EvidenceItem,
    Investigation,
    InvestigationStep,
    MetricObservation,
    Workspace,
)
from app.schemas.investigation import (
    CalculateMetricChangeInput,
    QueryMetricSeriesInput,
    QueryRelatedRecordsInput,
    RankEntityContributionsInput,
    SemanticDocumentSearchInput,
    TraverseRelationshipsInput,
)
from app.workspaces import get_mutable_workspace

SCOPED_MODELS = (
    DataSource,
    Document,
    DocumentChunk,
    Investigation,
    InvestigationStep,
    Entity,
    EntityRelationship,
    MetricObservation,
    BusinessRecord,
    EvidenceItem,
    Claim,
)


class EmptyResult:
    def all(self) -> list:
        return []

    def scalars(self) -> "EmptyResult":
        return self

    def __iter__(self):
        return iter(())


class CapturingSession:
    def __init__(self) -> None:
        self.statements = []

    async def execute(self, statement) -> EmptyResult:
        self.statements.append(statement)
        return EmptyResult()

    async def get(self, *_args):
        return None


def _sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _step(investigation_id: uuid.UUID, sequence: int = 1) -> InvestigationStep:
    return InvestigationStep(
        id=uuid.uuid4(),
        investigation_id=investigation_id,
        sequence=sequence,
        tool="test",
    )


def test_every_persisted_capability_has_required_workspace_scope() -> None:
    for model in SCOPED_MODELS:
        assert model.__table__.c.workspace_id.nullable is False

    entity_unique = {tuple(item.columns.keys()) for item in Entity.__table__.constraints}
    record_unique = {tuple(item.columns.keys()) for item in BusinessRecord.__table__.constraints}
    assert ("workspace_id", "entity_type", "external_key") in entity_unique
    assert ("workspace_id", "record_type", "external_key") in record_unique
    assert Document.__table__.c.data_source_id.nullable is True
    assert Document.__table__.c.source_item_id.nullable is True
    assert Document.__table__.c.source_synced_at.nullable is True
    source_foreign_keys = {
        tuple(constraint.column_keys)
        for constraint in Document.__table__.foreign_key_constraints
    }
    assert ("workspace_id", "data_source_id") in source_foreign_keys
    source_item_indexes = {
        tuple(index.columns.keys()) for index in Document.__table__.indexes if index.unique
    }
    assert ("workspace_id", "data_source_id", "source_item_id") in source_item_indexes


def test_workspace_header_is_required() -> None:
    response = TestClient(app).post("/api/v1/ask", json={"question": "hello"})
    assert response.status_code == 400
    assert response.json()["detail"] == "X-Workspace-ID is required."


@pytest.mark.asyncio
async def test_demo_workspace_rejects_mutation() -> None:
    demo = Workspace(
        id=DEMO_WORKSPACE_ID,
        name="Demo",
        owner_subject=None,
        is_demo=True,
    )
    with pytest.raises(HTTPException) as raised:
        await get_mutable_workspace(demo)
    assert raised.value.status_code == 403


def test_worker_contract_accepts_only_persisted_investigation_id() -> None:
    path = Path(__file__).resolve().parents[3] / "workers" / "celery" / "tasks.py"
    tree = ast.parse(path.read_text())
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_investigation"
    )
    assert [argument.arg for argument in function.args.args] == ["self", "investigation_id"]


@pytest.mark.asyncio
async def test_planner_metric_period_context_is_workspace_scoped() -> None:
    workspace_id = uuid.uuid4()
    other_workspace_id = uuid.uuid4()
    session = CapturingSession()
    orchestrator = InvestigationOrchestrator(session, deterministic=True)

    periods = await orchestrator._workspace_metric_periods(workspace_id)

    assert periods == ()
    statement = _sql(session.statements[-1])
    assert f"metric_observations.workspace_id = '{workspace_id}'" in statement
    assert str(other_workspace_id) not in statement
    assert "metric_observations.metric_key = 'recognized_revenue_usd'" in statement


@pytest.mark.asyncio
async def test_all_retrieval_tools_embed_workspace_predicates(monkeypatch) -> None:
    workspace_id = uuid.uuid4()
    investigation_id = uuid.uuid4()
    session = CapturingSession()
    executor = ToolExecutor(session, investigation_id, workspace_id, ExecutionBudget())

    with pytest.raises(RequiredDataError):
        await executor._query_metric_series(
            _step(investigation_id),
            QueryMetricSeriesInput(
                metric_key="recognized_revenue_usd",
                period_start=date(2026, 6, 1),
                period_end=date(2026, 7, 31),
            ),
        )
    assert "metric_observations.workspace_id" in _sql(session.statements[-1])

    entity_id = uuid.uuid4()
    executor.prior_outputs[1] = {
        "workspace_id": str(workspace_id),
        "contributions": [{"entity_id": str(entity_id)}],
    }
    await executor._query_related_records(
        _step(investigation_id, 2),
        QueryRelatedRecordsInput(entity_selector="top_contributor"),
    )
    assert "business_records.workspace_id" in _sql(session.statements[-1])

    await executor._traverse_relationships(
        _step(investigation_id, 3),
        TraverseRelationshipsInput(entity_selector="top_contributor"),
    )
    assert "relationships.workspace_id" in _sql(session.statements[-1])

    captured = {}

    async def fake_search(_db, scoped_workspace_id, _query, **_kwargs):
        captured["workspace_id"] = scoped_workspace_id
        return []

    monkeypatch.setattr(tools_module, "semantic_search", fake_search)
    await executor._semantic_document_search(
        _step(investigation_id, 4), SemanticDocumentSearchInput(query="renewal")
    )
    assert captured["workspace_id"] == workspace_id


@pytest.mark.asyncio
async def test_semantic_search_remains_workspace_wide_across_data_sources(monkeypatch) -> None:
    workspace_id = uuid.uuid4()
    session = CapturingSession()

    async def fake_embedding(_query: str) -> list[float]:
        return [0.0] * 1536

    monkeypatch.setattr(search_service, "generate_embedding", fake_embedding)
    assert await search_service.semantic_search(session, workspace_id, "revenue") == []
    statement = _sql(session.statements[-1])
    assert f"document_chunks.workspace_id = '{workspace_id}'" in statement
    assert f"documents.workspace_id = '{workspace_id}'" in statement
    where_clause = statement.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert "data_source_id" not in where_clause


@pytest.mark.asyncio
async def test_deterministic_tools_reject_untrusted_prior_workspace_outputs() -> None:
    workspace_id = uuid.uuid4()
    investigation_id = uuid.uuid4()
    executor = ToolExecutor(CapturingSession(), investigation_id, workspace_id, ExecutionBudget())
    executor.prior_outputs[1] = {
        "workspace_id": str(uuid.uuid4()),
        "observations": [{"period_start": "2026-06-01", "value": "1"}],
    }

    with pytest.raises(RequiredDataError, match="unavailable"):
        await executor._calculate_metric_change(
            _step(investigation_id, 2), CalculateMetricChangeInput(current_step=1)
        )
    with pytest.raises(RequiredDataError, match="unavailable"):
        await executor._rank_entity_contributions(
            _step(investigation_id, 3),
            RankEntityContributionsInput(
                metric_step=1,
                current_period_start=date(2026, 7, 1),
                comparison_period_start=date(2026, 6, 1),
            ),
        )


@pytest.mark.asyncio
async def test_cross_workspace_entity_ids_are_rejected() -> None:
    executor = ToolExecutor(
        CapturingSession(), uuid.uuid4(), uuid.uuid4(), ExecutionBudget()
    )
    with pytest.raises(RequiredDataError, match="not available"):
        await executor._validate_entity_ids([uuid.uuid4()])
