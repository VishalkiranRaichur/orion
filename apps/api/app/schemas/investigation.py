from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InvestigationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class InvestigationStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class InvestigationIntentType(StrEnum):
    FACTUAL = "factual"
    CAUSAL_ANALYSIS = "causal_analysis"
    COMPARISON = "comparison"
    TREND = "trend"
    ANOMALY = "anomaly"


class EntityType(StrEnum):
    CUSTOMER = "customer"
    PROJECT = "project"
    CONTRACT = "contract"


class BusinessRecordType(StrEnum):
    CRM_ACTIVITY = "crm_activity"
    SUPPORT_INCIDENT = "support_incident"
    PROJECT_UPDATE = "project_update"
    RENEWAL_EVENT = "renewal_event"


class EvidenceKind(StrEnum):
    METRIC_OBSERVATION = "metric_observation"
    BUSINESS_RECORD = "business_record"
    DOCUMENT_CHUNK = "document_chunk"
    RELATIONSHIP = "relationship"
    CALCULATION = "calculation"


class ClaimEvidenceRelationship(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"


class ComparisonKind(StrEnum):
    PREVIOUS_PERIOD = "previous_period"
    YEAR_OVER_YEAR = "year_over_year"
    CUSTOM = "custom"


class InvestigationTimeScope(StrictModel):
    start: date | None = None
    end: date | None = None
    label: str | None = None


class InvestigationIntent(StrictModel):
    kind: InvestigationIntentType
    metric: str | None = None
    time_scope: InvestigationTimeScope | None = None
    comparison: ComparisonKind | None = None
    entity_types: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    organization_scope: str = "company-wide"
    assumptions: list[str] = Field(default_factory=list)


class InvestigationToolKind(StrEnum):
    QUERY_METRIC_SERIES = "query_metric_series"
    CALCULATE_METRIC_CHANGE = "calculate_metric_change"
    RANK_ENTITY_CONTRIBUTIONS = "rank_entity_contributions"
    QUERY_RELATED_RECORDS = "query_related_records"
    SEMANTIC_DOCUMENT_SEARCH = "semantic_document_search"
    TRAVERSE_RELATIONSHIPS = "traverse_relationships"


class ToolArguments(StrictModel):
    pass


class QueryMetricSeriesInput(ToolArguments):
    metric_key: str
    period_start: date
    period_end: date
    entity_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def dates_are_ordered(self) -> QueryMetricSeriesInput:
        if self.period_start > self.period_end:
            raise ValueError("period_start must not be after period_end")
        return self


class CalculateMetricChangeInput(ToolArguments):
    current_step: int = Field(ge=1)
    comparison_step: int | None = Field(default=None, ge=1)
    current_period_start: date | None = None
    comparison_period_start: date | None = None


class RankEntityContributionsInput(ToolArguments):
    metric_step: int = Field(ge=1)
    current_period_start: date
    comparison_period_start: date
    limit: int = Field(default=10, ge=1, le=100)


class DynamicEntitySelector(StrEnum):
    TOP_CONTRIBUTOR = "top_contributor"


class QueryRelatedRecordsInput(ToolArguments):
    entity_ids: list[UUID] = Field(default_factory=list)
    entity_selector: DynamicEntitySelector | None = None
    record_types: list[BusinessRecordType] = Field(default_factory=list)
    start: datetime | None = None
    end: datetime | None = None
    limit: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def valid_scope(self) -> QueryRelatedRecordsInput:
        if not self.entity_ids and self.entity_selector is None:
            raise ValueError("entity_ids or entity_selector is required")
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must not be after end")
        return self


class SemanticDocumentSearchInput(ToolArguments):
    query: str = Field(default="investigation question", min_length=1, max_length=1000)
    entity_ids: list[UUID] = Field(default_factory=list)
    entity_selector: DynamicEntitySelector | None = None
    document_ids: list[UUID] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=10)


class TraverseRelationshipsInput(ToolArguments):
    entity_ids: list[UUID] = Field(default_factory=list)
    entity_selector: DynamicEntitySelector | None = None
    relationship_types: list[str] = Field(default_factory=list)
    depth: int = Field(default=1, ge=1, le=2)
    max_nodes: int = Field(default=50, ge=1, le=50)

    @model_validator(mode="after")
    def valid_scope(self) -> TraverseRelationshipsInput:
        if not self.entity_ids and self.entity_selector is None:
            raise ValueError("entity_ids or entity_selector is required")
        return self


ToolInput = Annotated[
    QueryMetricSeriesInput
    | CalculateMetricChangeInput
    | RankEntityContributionsInput
    | QueryRelatedRecordsInput
    | SemanticDocumentSearchInput
    | TraverseRelationshipsInput,
    Field(union_mode="left_to_right"),
]

TOOL_INPUT_TYPES: dict[InvestigationToolKind, type[ToolArguments]] = {
    InvestigationToolKind.QUERY_METRIC_SERIES: QueryMetricSeriesInput,
    InvestigationToolKind.CALCULATE_METRIC_CHANGE: CalculateMetricChangeInput,
    InvestigationToolKind.RANK_ENTITY_CONTRIBUTIONS: RankEntityContributionsInput,
    InvestigationToolKind.QUERY_RELATED_RECORDS: QueryRelatedRecordsInput,
    InvestigationToolKind.SEMANTIC_DOCUMENT_SEARCH: SemanticDocumentSearchInput,
    InvestigationToolKind.TRAVERSE_RELATIONSHIPS: TraverseRelationshipsInput,
}


class InvestigationToolCall(StrictModel):
    tool: InvestigationToolKind
    arguments: ToolInput = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_arguments_for_tool(self) -> InvestigationToolCall:
        input_type = TOOL_INPUT_TYPES[self.tool]
        if not isinstance(self.arguments, input_type):
            self.arguments = input_type.model_validate(self.arguments)
        return self


class PlannerQueryRelatedRecordsInput(QueryRelatedRecordsInput):
    entity_selector: Literal[DynamicEntitySelector.TOP_CONTRIBUTOR]


class PlannerTraverseRelationshipsInput(TraverseRelationshipsInput):
    entity_selector: Literal[DynamicEntitySelector.TOP_CONTRIBUTOR]


class PlannerQueryMetricSeriesToolCall(StrictModel):
    tool: Literal[InvestigationToolKind.QUERY_METRIC_SERIES]
    arguments: QueryMetricSeriesInput


class PlannerCalculateMetricChangeToolCall(StrictModel):
    tool: Literal[InvestigationToolKind.CALCULATE_METRIC_CHANGE]
    arguments: CalculateMetricChangeInput


class PlannerRankEntityContributionsToolCall(StrictModel):
    tool: Literal[InvestigationToolKind.RANK_ENTITY_CONTRIBUTIONS]
    arguments: RankEntityContributionsInput


class PlannerQueryRelatedRecordsToolCall(StrictModel):
    tool: Literal[InvestigationToolKind.QUERY_RELATED_RECORDS]
    arguments: PlannerQueryRelatedRecordsInput


class PlannerSemanticDocumentSearchToolCall(StrictModel):
    tool: Literal[InvestigationToolKind.SEMANTIC_DOCUMENT_SEARCH]
    arguments: SemanticDocumentSearchInput


class PlannerTraverseRelationshipsToolCall(StrictModel):
    tool: Literal[InvestigationToolKind.TRAVERSE_RELATIONSHIPS]
    arguments: PlannerTraverseRelationshipsInput


PlannerToolCall = Annotated[
    PlannerQueryMetricSeriesToolCall
    | PlannerCalculateMetricChangeToolCall
    | PlannerRankEntityContributionsToolCall
    | PlannerQueryRelatedRecordsToolCall
    | PlannerSemanticDocumentSearchToolCall
    | PlannerTraverseRelationshipsToolCall,
    Field(union_mode="left_to_right"),
]

PLANNER_TOOL_INPUT_TYPES: dict[InvestigationToolKind, type[ToolArguments]] = {
    InvestigationToolKind.QUERY_METRIC_SERIES: QueryMetricSeriesInput,
    InvestigationToolKind.CALCULATE_METRIC_CHANGE: CalculateMetricChangeInput,
    InvestigationToolKind.RANK_ENTITY_CONTRIBUTIONS: RankEntityContributionsInput,
    InvestigationToolKind.QUERY_RELATED_RECORDS: PlannerQueryRelatedRecordsInput,
    InvestigationToolKind.SEMANTIC_DOCUMENT_SEARCH: SemanticDocumentSearchInput,
    InvestigationToolKind.TRAVERSE_RELATIONSHIPS: PlannerTraverseRelationshipsInput,
}


class MetricObservationOutput(StrictModel):
    evidence_id: UUID
    observation_id: UUID
    entity_id: UUID | None
    entity_name: str | None
    period_start: date
    period_end: date
    value: str
    unit: str


class MetricSeriesOutput(StrictModel):
    observations: list[MetricObservationOutput]


class CalculationOutput(StrictModel):
    operation: str
    formula: str
    inputs: dict[str, str]
    result: str | None
    input_evidence_ids: list[UUID]


class ContributionOutput(StrictModel):
    entity_id: UUID
    entity_name: str
    comparison_value: str
    current_value: str
    change: str
    contribution_percentage: str | None
    input_evidence_ids: list[UUID]


class ContributionRankingOutput(StrictModel):
    total_change: str
    contributions: list[ContributionOutput]


class InvestigationToolResult(BaseModel):
    tool: InvestigationToolKind
    evidence_ids: list[UUID] = Field(default_factory=list)
    output: dict[str, Any] = Field(default_factory=dict)


class ClaimClassification(StrEnum):
    FACT = "fact"
    DERIVED = "derived"
    HYPOTHESIS = "hypothesis"


class ClaimValidationStatus(StrEnum):
    VALIDATED = "validated"
    REJECTED = "rejected"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvidenceGraphNodeKind(StrEnum):
    CLAIM = "claim"
    EVIDENCE = "evidence"
    ENTITY = "entity"
    METRIC = "metric"
    CALCULATION = "calculation"
    SOURCE = "source"


class EvidenceGraphEdgeKind(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    ABOUT_ENTITY = "about_entity"
    SOURCED_FROM = "sourced_from"
    INPUT_TO = "input_to"
    RELATES_TO = "relates_to"


class EvidenceGraphNode(BaseModel):
    id: str
    kind: EvidenceGraphNodeKind
    label: str
    classification: ClaimClassification | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class EvidenceGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: EvidenceGraphEdgeKind
    details: dict[str, Any] = Field(default_factory=dict)


class EvidenceGraph(BaseModel):
    nodes: list[EvidenceGraphNode] = Field(default_factory=list)
    edges: list[EvidenceGraphEdge] = Field(default_factory=list)


class SupportedBriefStatement(BaseModel):
    text: str = Field(min_length=1)
    claim_ids: list[UUID] = Field(min_length=1)


class ExecutiveBriefConfidenceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExecutiveBriefConfidence(BaseModel):
    score: float = Field(ge=0, le=1)
    level: ExecutiveBriefConfidenceLevel
    rationale: str = Field(min_length=1)


class ExecutiveBriefEvidence(BaseModel):
    evidence_id: UUID
    label: str = Field(min_length=1)
    claim_ids: list[UUID] = Field(default_factory=list)


class ExecutiveBriefUncertainty(BaseModel):
    text: str = Field(min_length=1)
    claim_ids: list[UUID] = Field(default_factory=list)


class ExecutiveBrief(BaseModel):
    what_happened: SupportedBriefStatement
    primary_driver: SupportedBriefStatement | None = None
    likely_explanation: SupportedBriefStatement | None = None
    confidence: ExecutiveBriefConfidence
    key_evidence: list[ExecutiveBriefEvidence] = Field(default_factory=list)
    uncertainties: list[ExecutiveBriefUncertainty] = Field(default_factory=list)
    recommended_follow_up_questions: list[str] = Field(default_factory=list)


class InvestigationPlanStep(StrictModel):
    sequence: int = Field(ge=1)
    description: str = Field(min_length=1)
    required: bool = True
    depends_on: list[Annotated[int, Field(ge=1)]] = Field(default_factory=list)
    tool_call: InvestigationToolCall


class InvestigationPlan(StrictModel):
    intent: InvestigationIntent
    steps: list[InvestigationPlanStep] = Field(default_factory=list, max_length=8)
    created_at: datetime | None = None

    @model_validator(mode="after")
    def valid_order_and_dependencies(self) -> InvestigationPlan:
        if not self.steps:
            raise ValueError("Investigation plans must contain at least one step")
        sequences = [step.sequence for step in self.steps]
        if sequences != list(range(1, len(self.steps) + 1)):
            raise ValueError("Plan step sequences must be contiguous and ordered")
        for step in self.steps:
            if any(dependency not in sequences for dependency in step.depends_on):
                raise ValueError("Plan dependencies must reference existing steps")
            if any(dependency >= step.sequence for dependency in step.depends_on):
                raise ValueError("Plan dependencies must reference earlier steps")
            if len(set(step.depends_on)) != len(step.depends_on):
                raise ValueError("Plan dependencies must be unique")
        return self


class PlannerInvestigationPlanStep(StrictModel):
    sequence: int = Field(ge=1)
    description: str = Field(min_length=1)
    required: bool = True
    depends_on: list[Annotated[int, Field(ge=1)]] = Field(default_factory=list)
    tool_call: PlannerToolCall


class PlannerInvestigationPlan(StrictModel):
    intent: InvestigationIntent
    steps: list[PlannerInvestigationPlanStep] = Field(default_factory=list, max_length=8)
    created_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_tool_contracts(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        for position, step in enumerate(value.get("steps", []), start=1):
            if not isinstance(step, dict) or not isinstance(step.get("tool_call"), dict):
                continue
            tool_call = step["tool_call"]
            try:
                tool = InvestigationToolKind(tool_call.get("tool"))
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Step {position} uses an unsupported investigation tool"
                ) from error
            try:
                PLANNER_TOOL_INPUT_TYPES[tool].model_validate(tool_call.get("arguments"))
            except ValidationError as error:
                message = error.errors(include_url=False)[0]["msg"]
                raise ValueError(
                    f"Step {position} has invalid {tool.value} arguments: {message}"
                ) from error
        return value

    def to_investigation_plan(self) -> InvestigationPlan:
        return InvestigationPlan.model_validate(self.model_dump(mode="python"))


class InvestigationCreateRequest(StrictModel):
    question: str = Field(min_length=3, max_length=2000)


class InvestigationCreatedResponse(BaseModel):
    id: UUID
    question: str
    status: InvestigationStatus
    created_at: datetime


class InvestigationStepResponse(BaseModel):
    sequence: int
    tool: str
    description: str
    required: bool
    depends_on: list[int]
    status: InvestigationStepStatus
    input: dict[str, Any]
    output: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None


class EvidenceItemResponse(BaseModel):
    id: UUID
    step_id: UUID | None
    evidence_kind: str
    source_kind: str
    source_id: str | None
    provenance_group: str
    source_locator: dict[str, Any]
    related_entity_ids: list[str]
    content: str | None
    payload: dict[str, Any]
    observed_at: datetime | None


class ClaimResponse(BaseModel):
    id: UUID
    classification: ClaimClassification
    statement: str
    confidence: float | None
    formula: str | None
    details: dict[str, Any]
    validation_status: ClaimValidationStatus
    evidence_ids: list[UUID] = Field(default_factory=list)


class InvestigationDetailResponse(InvestigationCreatedResponse):
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_code: str | None
    error: str | None
    intent: dict[str, Any] | None
    assumptions: list[str]
    plan: dict[str, Any] | None
    execution_usage: dict[str, Any]
    steps: list[InvestigationStepResponse]
    claims: list[ClaimResponse]
    evidence: list[EvidenceItemResponse]
    executive_brief: ExecutiveBrief | None
    evidence_graph: EvidenceGraph


class InvestigationHistoryItem(InvestigationCreatedResponse):
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    intent_summary: str | None
    brief_preview: str | None
    confidence_score: float | None
    confidence_level: ExecutiveBriefConfidenceLevel | None


class InvestigationHistoryResponse(BaseModel):
    items: list[InvestigationHistoryItem]
    next_cursor: str | None = None


def validate_executive_brief_references(
    brief: ExecutiveBrief,
    *,
    valid_claim_ids: set[UUID],
    valid_evidence_ids: set[UUID],
) -> None:
    referenced_claim_ids = set(brief.what_happened.claim_ids)

    for statement in (brief.primary_driver, brief.likely_explanation):
        if statement is not None:
            referenced_claim_ids.update(statement.claim_ids)

    for evidence in brief.key_evidence:
        if evidence.evidence_id not in valid_evidence_ids:
            raise ValueError(f"Unknown Executive Brief evidence ID: {evidence.evidence_id}")
        referenced_claim_ids.update(evidence.claim_ids)

    for uncertainty in brief.uncertainties:
        referenced_claim_ids.update(uncertainty.claim_ids)

    unknown_claim_ids = referenced_claim_ids - valid_claim_ids
    if unknown_claim_ids:
        unknown = ", ".join(sorted(str(claim_id) for claim_id in unknown_claim_ids))
        raise ValueError(f"Unknown Executive Brief claim IDs: {unknown}")
