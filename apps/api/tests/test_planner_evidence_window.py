"""Regression: model plans must search for causes before the period that changed.

Reproduces manual acceptance investigation c30c2083 (Oct 23, 2026). The model planner
limited query_related_records to July 1-31, so the May and June export incidents that
explain the July decline were never retrieved and the explanation could not validate.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.services.search_service as search_service
from alembic import command
from app.demo.orion_importer import import_orion_company
from app.investigations.orchestrator import InvestigationOrchestrator
from app.investigations.planner import canonicalize_plan
from app.models import DEMO_WORKSPACE_ID, Claim, Investigation
from app.schemas.investigation import (
    BusinessRecordType,
    CalculateMetricChangeInput,
    DynamicEntitySelector,
    InvestigationIntent,
    InvestigationIntentType,
    InvestigationPlan,
    InvestigationPlanStep,
    InvestigationToolCall,
    InvestigationToolKind,
    QueryMetricSeriesInput,
    QueryRelatedRecordsInput,
    RankEntityContributionsInput,
    TraverseRelationshipsInput,
)
from tests.test_data_source_migration import _database_url, temporary_database

DEMO_ROOT = Path(__file__).resolve().parents[3] / "demo" / "orion_company"


def live_model_plan(related_start: datetime | None = None) -> InvestigationPlan:
    """The plan the model planner produced in the failed acceptance run."""
    return InvestigationPlan(
        intent=InvestigationIntent(
            kind=InvestigationIntentType.CAUSAL_ANALYSIS, metric="recognized_revenue_usd"
        ),
        steps=[
            InvestigationPlanStep(
                sequence=1,
                description="Query the recognized revenue metric series",
                tool_call=InvestigationToolCall(
                    tool=InvestigationToolKind.QUERY_METRIC_SERIES,
                    arguments=QueryMetricSeriesInput(
                        metric_key="recognized_revenue_usd",
                        period_start=date(2026, 6, 1),
                        period_end=date(2026, 7, 31),
                    ),
                ),
            ),
            InvestigationPlanStep(
                sequence=2,
                description="Calculate the change in recognized revenue",
                depends_on=[1],
                tool_call=InvestigationToolCall(
                    tool=InvestigationToolKind.CALCULATE_METRIC_CHANGE,
                    arguments=CalculateMetricChangeInput(
                        current_step=1,
                        current_period_start=date(2026, 7, 1),
                        comparison_period_start=date(2026, 6, 1),
                    ),
                ),
            ),
            InvestigationPlanStep(
                sequence=3,
                description="Rank the top contributors",
                depends_on=[1],
                tool_call=InvestigationToolCall(
                    tool=InvestigationToolKind.RANK_ENTITY_CONTRIBUTIONS,
                    arguments=RankEntityContributionsInput(
                        metric_step=1,
                        current_period_start=date(2026, 7, 1),
                        comparison_period_start=date(2026, 6, 1),
                        limit=5,
                    ),
                ),
            ),
            InvestigationPlanStep(
                sequence=4,
                description="Query related records for the top contributors",
                required=False,
                depends_on=[3],
                tool_call=InvestigationToolCall(
                    tool=InvestigationToolKind.QUERY_RELATED_RECORDS,
                    arguments=QueryRelatedRecordsInput(
                        entity_selector=DynamicEntitySelector.TOP_CONTRIBUTOR,
                        record_types=[
                            BusinessRecordType.CRM_ACTIVITY,
                            BusinessRecordType.SUPPORT_INCIDENT,
                            BusinessRecordType.PROJECT_UPDATE,
                            BusinessRecordType.RENEWAL_EVENT,
                        ],
                        start=related_start or datetime(2026, 7, 1, tzinfo=UTC),
                        end=datetime(2026, 7, 31, 23, 59, 59, tzinfo=UTC),
                        limit=10,
                    ),
                ),
            ),
            InvestigationPlanStep(
                sequence=5,
                description="Traverse relationships of the top contributors",
                required=False,
                depends_on=[3],
                tool_call=InvestigationToolCall(
                    tool=InvestigationToolKind.TRAVERSE_RELATIONSHIPS,
                    arguments=TraverseRelationshipsInput(
                        entity_selector=DynamicEntitySelector.TOP_CONTRIBUTOR,
                        depth=2,
                        max_nodes=10,
                    ),
                ),
            ),
        ],
    )


def _related_arguments(plan: InvestigationPlan) -> QueryRelatedRecordsInput:
    arguments = plan.steps[3].tool_call.arguments
    assert isinstance(arguments, QueryRelatedRecordsInput)
    return arguments


def test_related_record_window_reaches_back_before_comparison_period() -> None:
    arguments = _related_arguments(canonicalize_plan(live_model_plan()))
    assert arguments.start == datetime(2026, 5, 1, tzinfo=UTC)
    assert arguments.end == datetime(2026, 7, 31, 23, 59, 59, tzinfo=UTC)


def test_related_record_window_that_already_reaches_back_is_unchanged() -> None:
    earlier = datetime(2026, 3, 15, tzinfo=UTC)
    arguments = _related_arguments(canonicalize_plan(live_model_plan(earlier)))
    assert arguments.start == earlier


class StaticPlanner:
    def __init__(self, plan: InvestigationPlan) -> None:
        self.plan = plan

    async def create_plan(self, question: str, *, metric_periods=()) -> InvestigationPlan:
        return self.plan


def test_live_model_plan_now_validates_the_demo_explanation(monkeypatch) -> None:
    with temporary_database() as (database, config):
        command.upgrade(config, "head")
        engine = create_async_engine(_database_url(database))
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async def embedding(_text: str) -> list[float]:
            return [1.0] + [0.0] * 1535

        async def processor(content: bytes, _filename: str) -> dict:
            return {"chunks": [content.decode()], "embeddings": [[1.0] + [0.0] * 1535]}

        monkeypatch.setattr(search_service, "generate_embedding", embedding)

        async def exercise() -> Claim:
            async with session_factory() as db:
                await import_orion_company(
                    db,
                    DEMO_ROOT,
                    upload=lambda _content, key, _type: key,
                    delete=lambda _key: None,
                    processor=processor,
                )
                investigation = Investigation(
                    question="Why did revenue decline in July?",
                    workspace_id=DEMO_WORKSPACE_ID,
                    created_by_subject="regression-test",
                )
                db.add(investigation)
                await db.commit()
                await InvestigationOrchestrator(
                    db, planner=StaticPlanner(live_model_plan())
                ).run(investigation.id)
                hypothesis = (
                    await db.execute(
                        select(Claim).where(
                            Claim.investigation_id == investigation.id,
                            Claim.classification == "hypothesis",
                        )
                    )
                ).scalar_one()
            await engine.dispose()
            return hypothesis

        hypothesis = asyncio.run(exercise())
        assert hypothesis.validation_status == "validated"
        assert hypothesis.confidence is not None
        assert hypothesis.confidence >= Decimal("0.70")
