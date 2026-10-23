import uuid

import pytest
from pydantic import ValidationError

from app.capabilities import CAPABILITY_STATES, Capability, CapabilityState
from app.schemas.investigation import (
    ExecutiveBrief,
    ExecutiveBriefConfidence,
    ExecutiveBriefConfidenceLevel,
    ExecutiveBriefEvidence,
    InvestigationIntent,
    InvestigationIntentType,
    InvestigationPlan,
    InvestigationPlanStep,
    InvestigationToolCall,
    InvestigationToolKind,
    PlannerInvestigationPlan,
    SupportedBriefStatement,
    validate_executive_brief_references,
)


def test_investigate_is_active_during_phase_two() -> None:
    assert CAPABILITY_STATES == {
        Capability.ASK: CapabilityState.ACTIVE,
        Capability.INVESTIGATE: CapabilityState.ACTIVE,
        Capability.WATCH: CapabilityState.INACTIVE,
        Capability.ACT: CapabilityState.INACTIVE,
    }


def test_investigation_plan_is_bounded_to_eight_steps() -> None:
    intent = InvestigationIntent(kind=InvestigationIntentType.CAUSAL_ANALYSIS)
    steps = [
        InvestigationPlanStep(
            sequence=index,
            description=f"Step {index}",
            tool_call=InvestigationToolCall(tool=InvestigationToolKind.SEMANTIC_DOCUMENT_SEARCH),
        )
        for index in range(1, 10)
    ]

    with pytest.raises(ValidationError):
        InvestigationPlan(intent=intent, steps=steps)


def test_investigation_plan_schema_has_only_strict_tool_argument_models() -> None:
    schema = InvestigationPlan.model_json_schema()
    arguments = schema["$defs"]["InvestigationToolCall"]["properties"]["arguments"]

    assert len(arguments["anyOf"]) == 6
    assert all(branch.keys() == {"$ref"} for branch in arguments["anyOf"])
    assert not any(
        definition.get("type") == "object"
        and definition.get("additionalProperties") is not False
        for definition in schema["$defs"].values()
    )


def test_planner_schema_binds_each_tool_name_to_its_argument_model() -> None:
    schema = PlannerInvestigationPlan.model_json_schema()
    tool_call = schema["$defs"]["PlannerInvestigationPlanStep"]["properties"]["tool_call"]
    expected = {
        "query_metric_series": "QueryMetricSeriesInput",
        "calculate_metric_change": "CalculateMetricChangeInput",
        "rank_entity_contributions": "RankEntityContributionsInput",
        "query_related_records": "PlannerQueryRelatedRecordsInput",
        "semantic_document_search": "SemanticDocumentSearchInput",
        "traverse_relationships": "PlannerTraverseRelationshipsInput",
    }

    assert len(tool_call["anyOf"]) == len(expected)
    for variant in tool_call["anyOf"]:
        definition = schema["$defs"][variant["$ref"].rsplit("/", 1)[-1]]
        tool = definition["properties"]["tool"]["const"]
        arguments = definition["properties"]["arguments"]["$ref"].rsplit("/", 1)[-1]
        assert arguments == expected[tool]

    def schema_nodes(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from schema_nodes(child)
        elif isinstance(value, list):
            for child in value:
                yield from schema_nodes(child)

    assert all("oneOf" not in node for node in schema_nodes(schema))
    assert not any(node.get("additionalProperties") is True for node in schema_nodes(schema))


def test_planner_schema_requires_top_contributor_for_entity_dependent_calls() -> None:
    schema = PlannerInvestigationPlan.model_json_schema()

    for definition_name in (
        "PlannerQueryRelatedRecordsInput",
        "PlannerTraverseRelationshipsInput",
    ):
        definition = schema["$defs"][definition_name]
        selector = definition["properties"]["entity_selector"]
        assert selector["const"] == "top_contributor"
        assert "null" not in selector.get("type", [])


def test_executive_brief_references_are_validated() -> None:
    claim_id = uuid.uuid4()
    evidence_id = uuid.uuid4()
    brief = ExecutiveBrief(
        what_happened=SupportedBriefStatement(
            text="Revenue declined in July.", claim_ids=[claim_id]
        ),
        confidence=ExecutiveBriefConfidence(
            score=0.8,
            level=ExecutiveBriefConfidenceLevel.HIGH,
            rationale="The measured change is supported by monthly observations.",
        ),
        key_evidence=[
            ExecutiveBriefEvidence(
                evidence_id=evidence_id,
                label="July revenue observation",
                claim_ids=[claim_id],
            )
        ],
    )

    validate_executive_brief_references(
        brief,
        valid_claim_ids={claim_id},
        valid_evidence_ids={evidence_id},
    )

    with pytest.raises(ValueError, match="Unknown Executive Brief evidence ID"):
        validate_executive_brief_references(
            brief,
            valid_claim_ids={claim_id},
            valid_evidence_ids=set(),
        )
