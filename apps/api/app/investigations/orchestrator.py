from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.investigations.budget import ExecutionBudget
from app.investigations.claims import build_and_validate_claims, build_executive_brief
from app.investigations.errors import InvestigationError, RequiredDataError
from app.investigations.planner import (
    DeterministicPlannerGateway,
    ModelPlannerGateway,
    PlannerGateway,
    canonicalize_plan,
)
from app.investigations.tools import ToolExecutor
from app.models import Investigation, InvestigationStep, MetricObservation
from app.schemas.investigation import (
    ClaimClassification,
    ClaimValidationStatus,
    InvestigationPlan,
    InvestigationStatus,
    InvestigationStepStatus,
)


class InvestigationOrchestrator:
    def __init__(
        self,
        db: AsyncSession,
        planner: PlannerGateway | None = None,
        *,
        deterministic: bool = False,
    ) -> None:
        self.db = db
        self.planner = planner or (
            DeterministicPlannerGateway() if deterministic else ModelPlannerGateway()
        )

    async def run(self, investigation_id: uuid.UUID) -> Investigation:
        investigation = await self._claim(investigation_id)
        if investigation.status in {
            InvestigationStatus.COMPLETED.value,
            InvestigationStatus.FAILED.value,
        }:
            return investigation

        budget = ExecutionBudget()
        try:
            plan = await self._plan(investigation, budget)
            steps = await self._upsert_steps(investigation, plan)
            executor = ToolExecutor(self.db, investigation.id, investigation.workspace_id, budget)
            optional_failures: list[str] = []
            steps_by_sequence = {step.sequence: step for step in steps}
            for step, planned in zip(steps, plan.steps, strict=True):
                if step.status == InvestigationStepStatus.COMPLETED.value:
                    executor.load_completed_output(step.sequence, step.output or {})
                    continue
                unavailable_dependencies = [
                    sequence
                    for sequence in planned.depends_on
                    if steps_by_sequence[sequence].status != InvestigationStepStatus.COMPLETED.value
                ]
                if unavailable_dependencies:
                    error = RequiredDataError(
                        "Required dependencies did not complete: "
                        + ", ".join(str(value) for value in unavailable_dependencies)
                    )
                    step.error = str(error)
                    step.completed_at = datetime.now(UTC)
                    if planned.required:
                        step.status = InvestigationStepStatus.FAILED.value
                        await self.db.commit()
                        raise error
                    step.status = InvestigationStepStatus.SKIPPED.value
                    optional_failures.append(
                        f"Optional {planned.tool_call.tool.value} evidence was skipped: {error}"
                    )
                    await self.db.commit()
                    continue
                budget.consume_step()
                step.status = InvestigationStepStatus.RUNNING.value
                step.started_at = datetime.now(UTC)
                await self.db.commit()
                try:
                    output = await executor.execute(step, planned.tool_call)
                except Exception as error:
                    step.error = str(error)[:1000]
                    step.completed_at = datetime.now(UTC)
                    if planned.required:
                        step.status = InvestigationStepStatus.FAILED.value
                        await self.db.commit()
                        raise
                    step.status = InvestigationStepStatus.SKIPPED.value
                    optional_failures.append(
                        f"Optional {planned.tool_call.tool.value} evidence was unavailable: {error}"
                    )
                else:
                    step.status = InvestigationStepStatus.COMPLETED.value
                    step.output = output
                    step.completed_at = datetime.now(UTC)
                    step.error = None
                investigation.execution_usage = budget.snapshot()
                investigation.updated_at = datetime.now(UTC)
                await self.db.commit()

            claims = await build_and_validate_claims(
                self.db, investigation.id, investigation.workspace_id
            )
            facts = [
                claim
                for claim in claims
                if claim.classification == ClaimClassification.FACT.value
                and claim.validation_status == ClaimValidationStatus.VALIDATED.value
            ]
            derived = [
                claim
                for claim in claims
                if claim.classification == ClaimClassification.DERIVED.value
                and claim.validation_status == ClaimValidationStatus.VALIDATED.value
            ]
            if not facts:
                raise RequiredDataError("Completion requires at least one validated fact")
            if plan.intent.metric and not derived:
                raise RequiredDataError(
                    "Metric investigations require at least one validated derived claim"
                )
            brief = await build_executive_brief(
                self.db, investigation.id, investigation.workspace_id, optional_failures
            )
            investigation.executive_brief = brief.model_dump(mode="json")
            investigation.summary = brief.what_happened.text
            investigation.status = InvestigationStatus.COMPLETED.value
            investigation.completed_at = datetime.now(UTC)
            investigation.updated_at = datetime.now(UTC)
            investigation.execution_usage = budget.snapshot()
            investigation.error = None
            investigation.failure_code = None
            await self.db.commit()
            return investigation
        except Exception:
            await self.db.rollback()
            raise

    async def _claim(self, investigation_id: uuid.UUID) -> Investigation:
        result = await self.db.execute(
            select(Investigation).where(Investigation.id == investigation_id).with_for_update()
        )
        investigation = result.scalar_one_or_none()
        if investigation is None:
            raise RequiredDataError(f"Investigation {investigation_id} does not exist")
        if investigation.status not in {
            InvestigationStatus.COMPLETED.value,
            InvestigationStatus.FAILED.value,
        }:
            investigation.status = InvestigationStatus.RUNNING.value
            investigation.started_at = investigation.started_at or datetime.now(UTC)
            investigation.updated_at = datetime.now(UTC)
            investigation.attempt_count += 1
            await self.db.commit()
        return investigation

    async def _plan(
        self, investigation: Investigation, budget: ExecutionBudget
    ) -> InvestigationPlan:
        if investigation.plan:
            return canonicalize_plan(InvestigationPlan.model_validate(investigation.plan))
        budget.consume_model()
        metric_periods = await self._workspace_metric_periods(investigation.workspace_id)
        plan = canonicalize_plan(
            await self.planner.create_plan(
                investigation.question,
                metric_periods=metric_periods,
            )
        )
        investigation.intent = plan.intent.model_dump(mode="json")
        investigation.assumptions = plan.intent.assumptions
        investigation.plan = plan.model_dump(mode="json")
        investigation.execution_usage = budget.snapshot()
        investigation.updated_at = datetime.now(UTC)
        await self.db.commit()
        return plan

    async def _workspace_metric_periods(
        self, workspace_id: uuid.UUID
    ) -> tuple[tuple[date, date], ...]:
        statement = (
            select(MetricObservation.period_start, MetricObservation.period_end)
            .where(
                MetricObservation.workspace_id == workspace_id,
                MetricObservation.metric_key == "recognized_revenue_usd",
            )
            .distinct()
            .order_by(MetricObservation.period_start, MetricObservation.period_end)
        )
        return tuple((await self.db.execute(statement)).all())

    async def _upsert_steps(
        self, investigation: Investigation, plan: InvestigationPlan
    ) -> list[InvestigationStep]:
        existing = {
            step.sequence: step
            for step in (
                (
                    await self.db.execute(
                        select(InvestigationStep).where(
                            InvestigationStep.investigation_id == investigation.id
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
        steps = []
        for planned in plan.steps:
            step = existing.get(planned.sequence)
            if step is None:
                step = InvestigationStep(
                    workspace_id=investigation.workspace_id,
                    investigation_id=investigation.id,
                    sequence=planned.sequence,
                    tool=planned.tool_call.tool.value,
                    input=planned.tool_call.arguments.model_dump(mode="json"),
                )
                self.db.add(step)
            steps.append(step)
        await self.db.commit()
        return steps


async def mark_failed(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    error: Exception,
    *,
    failure_code: str | None = None,
) -> None:
    investigation = await db.get(Investigation, investigation_id)
    if investigation is None or investigation.status == InvestigationStatus.COMPLETED.value:
        return
    investigation.status = InvestigationStatus.FAILED.value
    investigation.failure_code = failure_code or (
        error.code if isinstance(error, InvestigationError) else "unrecoverable_error"
    )
    investigation.error = str(error)[:1000] or "Investigation failed."
    investigation.completed_at = datetime.now(UTC)
    investigation.updated_at = datetime.now(UTC)
    await db.commit()
