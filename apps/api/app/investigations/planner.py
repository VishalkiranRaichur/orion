from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Protocol

from app.investigations.errors import PlanValidationError
from app.investigations.registry import ENABLED_TOOLS, resolve_metric
from app.schemas.investigation import (
    CalculateMetricChangeInput,
    InvestigationIntent,
    InvestigationIntentType,
    InvestigationPlan,
    InvestigationPlanStep,
    InvestigationToolCall,
    InvestigationToolKind,
    PlannerInvestigationPlan,
    QueryMetricSeriesInput,
    QueryRelatedRecordsInput,
    RankEntityContributionsInput,
    SemanticDocumentSearchInput,
    TraverseRelationshipsInput,
)
from app.services.structured_response import parse_structured_response

MetricPeriod = tuple[date, date]

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def build_planner_input(question: str, metric_periods: tuple[MetricPeriod, ...]) -> str:
    lines = [f"USER QUESTION:\n{question}"]
    if not metric_periods:
        lines.append("WORKSPACE METRIC AVAILABILITY:\nNo recognized revenue periods are available.")
        return "\n\n".join(lines)

    ordered = sorted(set(metric_periods))
    availability = "\n".join(
        f"- recognized_revenue_usd: {period_start.isoformat()} through {period_end.isoformat()}"
        for period_start, period_end in ordered
    )
    lines.append(f"WORKSPACE METRIC AVAILABILITY:\n{availability}")

    lowered = question.lower()
    has_explicit_year = re.search(r"\b(?:19|20)\d{2}\b", question) is not None
    mentioned_months = [
        number for name, number in MONTHS.items() if re.search(rf"\b{name}\b", lowered)
    ]
    if mentioned_months and not has_explicit_year:
        candidates = [period for period in ordered if period[0].month in mentioned_months]
        if candidates:
            current = candidates[-1]
            previous = next(
                (period for period in reversed(ordered) if period[0] < current[0]), None
            )
            resolution = (
                "Resolve the ambiguous month to the latest matching workspace period: "
                f"current={current[0].isoformat()} through {current[1].isoformat()}."
            )
            if previous:
                resolution += (
                    " Use the immediately preceding available period for comparison: "
                    f"comparison={previous[0].isoformat()} through {previous[1].isoformat()}."
                )
            lines.append(f"DATE RESOLUTION:\n{resolution}")
    return "\n\n".join(lines)


class PlannerGateway(Protocol):
    async def create_plan(
        self, question: str, *, metric_periods: tuple[MetricPeriod, ...] = ()
    ) -> InvestigationPlan: ...


class ModelPlannerGateway:
    async def create_plan(
        self, question: str, *, metric_periods: tuple[MetricPeriod, ...] = ()
    ) -> InvestigationPlan:
        plan = await parse_structured_response(
            response_type=PlannerInvestigationPlan,
            instructions=(
                "Create one bounded recognized-revenue investigation plan using only the supplied "
                "schema and allowlisted tools. Never emit SQL. Use at most eight sequential steps. "
                "Use exactly one query_metric_series step spanning the comparison-period start "
                "through the current-period end. Both calculate_metric_change.current_step and "
                "rank_entity_contributions.metric_step must reference that same metric-query step, "
                "and both steps must directly depend on it. Set "
                "calculate_metric_change.comparison_step to null. Calls to "
                "query_related_records or traverse_relationships must occur after the ranking "
                "step, depend on that step, and use entity_selector=top_contributor. Do not invent "
                "entity UUIDs or dates outside WORKSPACE METRIC AVAILABILITY. Treat supporting "
                "record, document, and relationship searches as optional."
            ),
            input_text=build_planner_input(question, metric_periods),
        )
        return plan.to_investigation_plan()


class DeterministicPlannerGateway:
    """Deterministic adapter used by CI and the ORION demo evaluation."""

    async def create_plan(
        self, question: str, *, metric_periods: tuple[MetricPeriod, ...] = ()
    ) -> InvestigationPlan:
        lowered = question.lower()
        if "revenue" not in lowered or "july" not in lowered:
            raise PlanValidationError(
                "The deterministic planner only supports the July revenue demo"
            )
        metric = "recognized_revenue_usd"
        steps = [
            InvestigationPlanStep(
                sequence=1,
                description="Retrieve June and July revenue by customer",
                tool_call=InvestigationToolCall(
                    tool=InvestigationToolKind.QUERY_METRIC_SERIES,
                    arguments=QueryMetricSeriesInput(
                        metric_key=metric,
                        period_start=date(2026, 6, 1),
                        period_end=date(2026, 7, 31),
                    ),
                ),
            ),
            InvestigationPlanStep(
                sequence=2,
                description="Calculate total revenue change",
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
                description="Rank customer contribution to the decline",
                depends_on=[1],
                tool_call=InvestigationToolCall(
                    tool=InvestigationToolKind.RANK_ENTITY_CONTRIBUTIONS,
                    arguments=RankEntityContributionsInput(
                        metric_step=1,
                        current_period_start=date(2026, 7, 1),
                        comparison_period_start=date(2026, 6, 1),
                    ),
                ),
            ),
            InvestigationPlanStep(
                sequence=4,
                description="Retrieve records for the largest contributor",
                required=False,
                depends_on=[3],
                tool_call=InvestigationToolCall(
                    tool=InvestigationToolKind.QUERY_RELATED_RECORDS,
                    arguments=QueryRelatedRecordsInput(
                        entity_selector="top_contributor",
                        start=datetime(2026, 5, 1, tzinfo=UTC),
                        end=datetime(2026, 7, 31, 23, 59, tzinfo=UTC),
                    ),
                ),
            ),
            InvestigationPlanStep(
                sequence=5,
                description="Traverse relationships for the largest contributor",
                required=False,
                depends_on=[3],
                tool_call=InvestigationToolCall(
                    tool=InvestigationToolKind.TRAVERSE_RELATIONSHIPS,
                    arguments=TraverseRelationshipsInput(
                        entity_selector="top_contributor", depth=2
                    ),
                ),
            ),
            InvestigationPlanStep(
                sequence=6,
                description="Search supporting documents",
                required=False,
                depends_on=[3],
                tool_call=InvestigationToolCall(
                    tool=InvestigationToolKind.SEMANTIC_DOCUMENT_SEARCH,
                    arguments=SemanticDocumentSearchInput(
                        query="Northstar renewal export failures remediation delay",
                        entity_selector="top_contributor",
                        limit=10,
                    ),
                ),
            ),
        ]
        return InvestigationPlan(
            intent=InvestigationIntent(
                kind=InvestigationIntentType.CAUSAL_ANALYSIS,
                metric=metric,
                organization_scope="company-wide",
                assumptions=["The latest available July (July 2026) was intended."],
            ),
            steps=steps,
            created_at=datetime.now(UTC),
        )



CAUSAL_LOOKBACK_MONTHS = 1


def _months_before(value: date, months: int) -> date:
    """Return the first day of the month `months` before `value`'s month."""
    index = value.year * 12 + (value.month - 1) - months
    return date(index // 12, index % 12 + 1, 1)


def _widen_causal_evidence_windows(plan: InvestigationPlan) -> None:
    """Make related-record searches reach back before the comparison period.

    Causes precede their effects: an incident or slipped project that explains a
    July decline usually happens in May or June. A planner that limits the search
    to the period of the change would silently miss that evidence, so the window
    is widened here, independent of what the model proposed.
    """
    comparison_starts = [
        step.tool_call.arguments.comparison_period_start
        for step in plan.steps
        if step.tool_call.tool == InvestigationToolKind.RANK_ENTITY_CONTRIBUTIONS
    ]
    if not comparison_starts:
        return
    lookback = _months_before(min(comparison_starts), CAUSAL_LOOKBACK_MONTHS)
    lookback_start = datetime(lookback.year, lookback.month, lookback.day, tzinfo=UTC)
    for step in plan.steps:
        if step.tool_call.tool != InvestigationToolKind.QUERY_RELATED_RECORDS:
            continue
        arguments = step.tool_call.arguments
        assert isinstance(arguments, QueryRelatedRecordsInput)
        if arguments.start is not None and arguments.start > lookback_start:
            arguments.start = lookback_start


def canonicalize_plan(plan: InvestigationPlan) -> InvestigationPlan:
    if len(plan.steps) > 8:
        raise PlanValidationError("Plans may contain at most eight steps")
    if not plan.intent.metric:
        raise PlanValidationError(
            "Phase 2 supports recognized-revenue metric investigations only"
        )
    plan.intent.metric = resolve_metric(plan.intent.metric)
    steps_by_sequence = {step.sequence: step for step in plan.steps}
    tools_by_sequence = {step.sequence: step.tool_call.tool for step in plan.steps}
    for step in plan.steps:
        if step.tool_call.tool not in ENABLED_TOOLS:
            raise PlanValidationError(f"Unknown tool: {step.tool_call.tool}")
        if step.tool_call.tool == InvestigationToolKind.QUERY_METRIC_SERIES:
            arguments = step.tool_call.arguments
            assert isinstance(arguments, QueryMetricSeriesInput)
            arguments.metric_key = resolve_metric(arguments.metric_key)

        referenced_steps: list[tuple[int, InvestigationToolKind]] = []
        if step.tool_call.tool == InvestigationToolKind.CALCULATE_METRIC_CHANGE:
            arguments = step.tool_call.arguments
            assert isinstance(arguments, CalculateMetricChangeInput)
            referenced_steps.append(
                (arguments.current_step, InvestigationToolKind.QUERY_METRIC_SERIES)
            )
            if arguments.comparison_step:
                referenced_steps.append(
                    (arguments.comparison_step, InvestigationToolKind.QUERY_METRIC_SERIES)
                )
        elif step.tool_call.tool == InvestigationToolKind.RANK_ENTITY_CONTRIBUTIONS:
            arguments = step.tool_call.arguments
            assert isinstance(arguments, RankEntityContributionsInput)
            referenced_steps.append(
                (arguments.metric_step, InvestigationToolKind.QUERY_METRIC_SERIES)
            )

        for referenced_sequence, expected_tool in referenced_steps:
            if referenced_sequence >= step.sequence:
                raise PlanValidationError("Tool inputs must reference earlier plan steps")
            if tools_by_sequence.get(referenced_sequence) != expected_tool:
                raise PlanValidationError(
                    f"Step {referenced_sequence} must use {expected_tool.value}"
                )
            if referenced_sequence not in step.depends_on:
                raise PlanValidationError(
                    f"Step {step.sequence} must depend on referenced step {referenced_sequence}"
                )

        if step.tool_call.tool == InvestigationToolKind.RANK_ENTITY_CONTRIBUTIONS:
            arguments = step.tool_call.arguments
            assert isinstance(arguments, RankEntityContributionsInput)
            metric_step = steps_by_sequence[arguments.metric_step]
            metric_arguments = metric_step.tool_call.arguments
            assert isinstance(metric_arguments, QueryMetricSeriesInput)
            if not (
                metric_arguments.period_start <= arguments.comparison_period_start
                and metric_arguments.period_end >= arguments.current_period_start
            ):
                raise PlanValidationError(
                    "rank_entity_contributions metric_step must cover both comparison and "
                    "current periods"
                )

        selector = getattr(step.tool_call.arguments, "entity_selector", None)
        if selector is not None:
            ranking_steps = [
                sequence
                for sequence, tool in tools_by_sequence.items()
                if sequence < step.sequence
                and tool == InvestigationToolKind.RANK_ENTITY_CONTRIBUTIONS
            ]
            if not ranking_steps:
                raise PlanValidationError(
                    "Dynamic entity selectors require an earlier ranking step"
                )
            if not any(sequence in step.depends_on for sequence in ranking_steps):
                raise PlanValidationError(
                    "Dynamic entity selectors must depend on an earlier ranking step"
                )

    present = {step.tool_call.tool for step in plan.steps if step.required}
    required = {
        InvestigationToolKind.QUERY_METRIC_SERIES,
        InvestigationToolKind.CALCULATE_METRIC_CHANGE,
        InvestigationToolKind.RANK_ENTITY_CONTRIBUTIONS,
    }
    missing = required - present
    if missing:
        names = ", ".join(sorted(item.value for item in missing))
        raise PlanValidationError(f"Metric plan is missing required steps: {names}")
    _widen_causal_evidence_windows(plan)
    return InvestigationPlan.model_validate(plan.model_dump())
