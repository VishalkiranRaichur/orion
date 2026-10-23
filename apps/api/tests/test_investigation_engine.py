import csv
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app.investigations.tools as tools_module
import app.routers.investigations as investigations_router
from app.auth import Principal
from app.investigations.budget import ExecutionBudget
from app.investigations.errors import ExecutionLimitError, PlanValidationError
from app.investigations.planner import (
    DeterministicPlannerGateway,
    ModelPlannerGateway,
    build_planner_input,
    canonicalize_plan,
)
from app.investigations.tools import ToolExecutor, decimal_string
from app.models import Investigation, InvestigationStep, Workspace
from app.schemas.investigation import (
    InvestigationCreateRequest,
    InvestigationPlan,
    InvestigationStatus,
    PlannerInvestigationPlan,
    SemanticDocumentSearchInput,
)

DEMO_ROOT = Path(__file__).resolve().parents[3] / "demo" / "orion_company"


@pytest.mark.asyncio
async def test_deterministic_plan_is_canonical_and_bounded() -> None:
    plan = canonicalize_plan(
        await DeterministicPlannerGateway().create_plan("Why did revenue decline in July?")
    )

    assert len(plan.steps) == 6
    assert plan.intent.metric == "recognized_revenue_usd"
    assert [step.sequence for step in plan.steps] == list(range(1, 7))
    metric_arguments = plan.steps[0].tool_call.arguments
    calculation_arguments = plan.steps[1].tool_call.arguments
    ranking_arguments = plan.steps[2].tool_call.arguments
    assert metric_arguments.period_start == date(2026, 6, 1)
    assert metric_arguments.period_end == date(2026, 7, 31)
    assert calculation_arguments.current_step == ranking_arguments.metric_step == 1
    assert calculation_arguments.comparison_step is None
    assert plan.steps[1].depends_on == plan.steps[2].depends_on == [1]


@pytest.mark.asyncio
async def test_valid_top_contributor_planner_plan_parses_and_canonicalizes() -> None:
    runtime_plan = await DeterministicPlannerGateway().create_plan(
        "Why did revenue decline in July?"
    )

    planner_plan = PlannerInvestigationPlan.model_validate(runtime_plan.model_dump(mode="json"))
    canonical = canonicalize_plan(planner_plan.to_investigation_plan())

    assert canonical.steps[3].tool_call.arguments.entity_selector == "top_contributor"
    assert canonical.steps[3].depends_on == [3]
    assert canonical.steps[4].tool_call.arguments.entity_selector == "top_contributor"
    assert canonical.steps[4].depends_on == [3]


@pytest.mark.asyncio
async def test_malformed_entity_scope_fails_with_one_tool_specific_error() -> None:
    runtime_plan = await DeterministicPlannerGateway().create_plan(
        "Why did revenue decline in July?"
    )
    malformed = runtime_plan.model_dump(mode="json")
    malformed["steps"][3]["tool_call"]["arguments"].update(
        {"entity_ids": [], "entity_selector": None}
    )

    with pytest.raises(ValidationError) as raised:
        PlannerInvestigationPlan.model_validate(malformed)

    assert raised.value.error_count() == 1
    assert "invalid query_related_records arguments" in str(raised.value)
    assert "top_contributor" in str(raised.value)


def test_ambiguous_july_uses_latest_workspace_metric_period() -> None:
    planner_input = build_planner_input(
        "Why did revenue decline in July?",
        (
            (date(2025, 7, 1), date(2025, 7, 31)),
            (date(2026, 6, 1), date(2026, 6, 30)),
            (date(2026, 7, 1), date(2026, 7, 31)),
        ),
    )

    assert "current=2026-07-01 through 2026-07-31" in planner_input
    assert "comparison=2026-06-01 through 2026-06-30" in planner_input


@pytest.mark.asyncio
async def test_model_planner_receives_dependency_contract_and_date_context(monkeypatch) -> None:
    runtime_plan = await DeterministicPlannerGateway().create_plan(
        "Why did revenue decline in July?"
    )
    captured = {}

    async def fake_parse_structured_response(**kwargs):
        captured.update(kwargs)
        return PlannerInvestigationPlan.model_validate(runtime_plan.model_dump(mode="json"))

    monkeypatch.setattr(
        "app.investigations.planner.parse_structured_response", fake_parse_structured_response
    )

    plan = await ModelPlannerGateway().create_plan(
        "Why did revenue decline in July?",
        metric_periods=(
            (date(2026, 6, 1), date(2026, 6, 30)),
            (date(2026, 7, 1), date(2026, 7, 31)),
        ),
    )

    assert isinstance(plan, InvestigationPlan)
    assert "exactly one query_metric_series step" in captured["instructions"]
    assert "calculate_metric_change.current_step" in captured["instructions"]
    assert "calculate_metric_change.comparison_step to null" in captured["instructions"]
    assert "rank_entity_contributions.metric_step" in captured["instructions"]
    assert "both steps must directly depend on it" in captured["instructions"]
    assert "must occur after the ranking step" in captured["instructions"]
    assert "entity_selector=top_contributor" in captured["instructions"]
    assert "current=2026-07-01 through 2026-07-31" in captured["input_text"]


@pytest.mark.asyncio
async def test_phase_two_rejects_non_metric_plans() -> None:
    plan = await DeterministicPlannerGateway().create_plan(
        "Why did revenue decline in July?"
    )
    plan.intent.metric = None

    with pytest.raises(PlanValidationError, match="recognized-revenue"):
        canonicalize_plan(plan)


@pytest.mark.asyncio
async def test_plan_rejects_forward_tool_input_references() -> None:
    plan = await DeterministicPlannerGateway().create_plan(
        "Why did revenue decline in July?"
    )
    plan.steps[1].tool_call.arguments.current_step = 3

    with pytest.raises(PlanValidationError, match="earlier plan steps"):
        canonicalize_plan(plan)


@pytest.mark.asyncio
async def test_plan_requires_declared_tool_input_dependency() -> None:
    plan = await DeterministicPlannerGateway().create_plan(
        "Why did revenue decline in July?"
    )
    plan.steps[1].depends_on = []

    with pytest.raises(PlanValidationError, match="must depend on referenced step"):
        canonicalize_plan(plan)


@pytest.mark.asyncio
async def test_captured_split_period_plan_fails_at_direct_dependency() -> None:
    plan = await DeterministicPlannerGateway().create_plan(
        "Why did revenue decline in July?"
    )
    july_query = plan.steps[0].model_copy(deep=True)
    july_query.tool_call.arguments.period_start = date(2026, 7, 1)
    june_query = plan.steps[0].model_copy(deep=True)
    june_query.sequence = 2
    june_query.tool_call.arguments.period_end = date(2026, 6, 30)
    calculation = plan.steps[1].model_copy(deep=True)
    calculation.sequence = 3
    calculation.depends_on = [1, 2]
    calculation.tool_call.arguments.current_step = 2
    calculation.tool_call.arguments.comparison_step = 1
    ranking = plan.steps[2].model_copy(deep=True)
    ranking.sequence = 4
    ranking.depends_on = [3]
    ranking.tool_call.arguments.metric_step = 2
    plan.steps = [july_query, june_query, calculation, ranking]

    with pytest.raises(
        PlanValidationError, match="Step 4 must depend on referenced step 2"
    ):
        canonicalize_plan(plan)


@pytest.mark.asyncio
async def test_ranking_rejects_single_period_metric_output() -> None:
    plan = await DeterministicPlannerGateway().create_plan(
        "Why did revenue decline in July?"
    )
    plan.steps[0].tool_call.arguments.period_end = date(2026, 6, 30)

    with pytest.raises(PlanValidationError, match="must cover both comparison and current"):
        canonicalize_plan(plan)


def test_decimal_values_are_never_converted_through_float() -> None:
    value = Decimal("9007199254740993.123400")

    assert decimal_string(value) == "9007199254740993.1234"


def test_execution_budget_rejects_calls_past_limit(monkeypatch) -> None:
    monkeypatch.setattr("app.investigations.budget.settings.investigation_max_model_calls", 1)
    budget = ExecutionBudget()

    budget.consume_model()
    with pytest.raises(ExecutionLimitError, match="model-call"):
        budget.consume_model()


def test_history_confidence_is_derived_from_valid_brief() -> None:
    score, level = investigations_router._brief_confidence(
        {
            "what_happened": {"text": "Revenue declined.", "claim_ids": [str(uuid.uuid4())]},
            "confidence": {
                "score": 0.84,
                "level": "high",
                "rationale": "Measured evidence is validated.",
            },
        }
    )

    assert score == 0.84
    assert level == "high"
    assert investigations_router._brief_confidence({"invalid": True}) == (None, None)


def test_detail_step_metadata_uses_plan_and_safe_fallbacks() -> None:
    plan = {
        "steps": [
            {
                "sequence": 2,
                "description": "Calculate the revenue change",
                "required": False,
                "depends_on": [1],
            }
        ]
    }

    assert investigations_router._step_metadata(plan, 2, "calculate_metric_change") == (
        "Calculate the revenue change",
        False,
        [1],
    )
    assert investigations_router._step_metadata(None, 1, "query_metric_series") == (
        "Query Metric Series",
        True,
        [],
    )


class ScalarResult:
    def __init__(self, values: list | None = None) -> None:
        self.values = values or []

    def scalars(self) -> list:
        return self.values


class EmptyDatabase:
    async def execute(self, _statement) -> ScalarResult:
        return ScalarResult()


class ValidEntityEmptyDocumentsDatabase:
    def __init__(self, entity_id: uuid.UUID) -> None:
        self.entity_id = entity_id
        self.calls = 0

    async def execute(self, _statement) -> ScalarResult:
        self.calls += 1
        return ScalarResult([self.entity_id] if self.calls == 1 else [])


@pytest.mark.asyncio
async def test_entity_scoped_search_does_not_fall_back_to_global_corpus(monkeypatch) -> None:
    async def unexpected_search(*_args, **_kwargs):
        pytest.fail("semantic_search must not run without entity-linked documents")

    monkeypatch.setattr(tools_module, "semantic_search", unexpected_search)
    investigation_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    executor = ToolExecutor(
        ValidEntityEmptyDocumentsDatabase(entity_id),
        investigation_id,
        workspace_id,
        ExecutionBudget(),
    )
    step = InvestigationStep(
        id=uuid.uuid4(),
        investigation_id=investigation_id,
        sequence=1,
        tool="semantic_document_search",
    )

    result = await executor._semantic_document_search(
        step,
        SemanticDocumentSearchInput(query="renewal", entity_ids=[entity_id]),
    )

    assert result == {"chunks": [], "evidence_ids": []}


def test_demo_fixture_matches_expected_deterministic_calculations() -> None:
    expected = json.loads((DEMO_ROOT / "expected_findings.json").read_text())
    with (DEMO_ROOT / "revenue.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    june = sum(
        Decimal(row["recognized_revenue_usd"])
        for row in rows
        if row["period_start"] == "2026-06-01"
    )
    july = sum(
        Decimal(row["recognized_revenue_usd"])
        for row in rows
        if row["period_start"] == "2026-07-01"
    )
    change = july - june
    northstar = next(
        Decimal(row["recognized_revenue_usd"])
        for row in rows
        if row["customer_id"] == "northstar" and row["period_start"] == "2026-07-01"
    ) - next(
        Decimal(row["recognized_revenue_usd"])
        for row in rows
        if row["customer_id"] == "northstar" and row["period_start"] == "2026-06-01"
    )

    assert decimal_string(june) == expected["comparison_total"]
    assert decimal_string(july) == expected["current_total"]
    assert decimal_string(change) == expected["absolute_change"]
    assert decimal_string(change / june * Decimal(100)) == expected["percentage_change"]
    assert decimal_string(northstar) == expected["primary_entity_change"]
    assert decimal_string((northstar / change * Decimal(100)).quantize(Decimal("0.0001"))) == (
        expected["contribution_percentage"]
    )


class CreateSession:
    def __init__(self) -> None:
        self.investigation: Investigation | None = None

    def add(self, investigation: Investigation) -> None:
        self.investigation = investigation

    async def commit(self) -> None:
        assert self.investigation is not None
        now = datetime.now(UTC)
        self.investigation.id = self.investigation.id or uuid.uuid4()
        self.investigation.status = self.investigation.status or InvestigationStatus.QUEUED.value
        self.investigation.created_at = self.investigation.created_at or now
        self.investigation.updated_at = self.investigation.updated_at or now

    async def refresh(self, _investigation: Investigation) -> None:
        return None


@pytest.mark.asyncio
async def test_create_investigation_enqueues_stable_task_id(monkeypatch) -> None:
    calls = []

    def send_task(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(investigations_router.celery_client, "send_task", send_task)
    session = CreateSession()

    investigation = await investigations_router.create_investigation(
        InvestigationCreateRequest(question="Why did revenue decline in July?"),
        Workspace(id=uuid.uuid4(), name="A", owner_subject="user-a", is_demo=False),
        Principal("user-a"),
        session,
    )

    assert investigation.status == InvestigationStatus.QUEUED.value
    assert calls == [
        (
            ("orion.run_investigation",),
            {
                "args": [str(investigation.id)],
                "task_id": str(investigation.id),
                "queue": "investigations",
            },
        )
    ]


@pytest.mark.asyncio
async def test_create_investigation_persists_enqueue_failure(monkeypatch) -> None:
    def send_task(*_args, **_kwargs):
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr(investigations_router.celery_client, "send_task", send_task)
    session = CreateSession()

    with pytest.raises(HTTPException) as raised:
        await investigations_router.create_investigation(
            InvestigationCreateRequest(question="Why did revenue decline in July?"),
            Workspace(id=uuid.uuid4(), name="A", owner_subject="user-a", is_demo=False),
            Principal("user-a"),
            session,
        )

    assert raised.value.status_code == 503
    assert session.investigation is not None
    assert session.investigation.status == InvestigationStatus.FAILED.value
    assert session.investigation.failure_code == "enqueue_failed"
