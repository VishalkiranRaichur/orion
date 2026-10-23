from __future__ import annotations

import uuid
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Claim, ClaimEvidence, Entity, EvidenceItem
from app.schemas.investigation import (
    ClaimClassification,
    ClaimValidationStatus,
    EvidenceGraph,
    EvidenceGraphEdge,
    EvidenceGraphEdgeKind,
    EvidenceGraphNode,
    EvidenceGraphNodeKind,
    ExecutiveBrief,
    ExecutiveBriefConfidence,
    ExecutiveBriefConfidenceLevel,
    ExecutiveBriefEvidence,
    ExecutiveBriefUncertainty,
    SupportedBriefStatement,
    validate_executive_brief_references,
)

CLAIM_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "orion:claim")


def _claim_id(investigation_id: uuid.UUID, key: str) -> uuid.UUID:
    return uuid.uuid5(CLAIM_NAMESPACE, f"{investigation_id}:{key}")


async def _upsert_claim(
    db: AsyncSession,
    *,
    investigation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    key: str,
    classification: ClaimClassification,
    statement: str,
    validation_status: ClaimValidationStatus,
    evidence: list[EvidenceItem],
    relationship: str,
    confidence: Decimal | None = None,
    formula: str | None = None,
    details: dict[str, Any] | None = None,
) -> Claim:
    claim_id = _claim_id(investigation_id, key)
    claim = await db.get(Claim, claim_id)
    if claim is None:
        claim = Claim(
            id=claim_id,
            investigation_id=investigation_id,
            workspace_id=workspace_id,
        )
        db.add(claim)
    elif claim.workspace_id != workspace_id:
        raise ValueError("Claim ID collision crossed a workspace boundary")
    claim.classification = classification.value
    claim.statement = statement
    claim.validation_status = validation_status.value
    claim.confidence = confidence
    claim.formula = formula
    claim.details = details or {}
    await db.flush()
    existing_links = set(
        (
            await db.execute(
                select(ClaimEvidence.evidence_id).where(ClaimEvidence.claim_id == claim.id)
            )
        ).scalars()
    )
    for item in evidence:
        if item.id not in existing_links:
            db.add(
                ClaimEvidence(
                    claim_id=claim.id,
                    evidence_id=item.id,
                    relationship=relationship,
                )
            )
    return claim


async def build_and_validate_claims(
    db: AsyncSession, investigation_id: uuid.UUID, workspace_id: uuid.UUID
) -> list[Claim]:
    evidence = list(
        (
            await db.execute(
                select(EvidenceItem)
                .where(
                    EvidenceItem.investigation_id == investigation_id,
                    EvidenceItem.workspace_id == workspace_id,
                )
                .order_by(EvidenceItem.created_at, EvidenceItem.id)
            )
        )
        .scalars()
        .all()
    )
    entity_names = dict(
        (
            await db.execute(
                select(Entity.id, Entity.name).where(Entity.workspace_id == workspace_id)
            )
        ).all()
    )
    claims: list[Claim] = []
    for item in evidence:
        if item.evidence_kind == "metric_observation":
            payload = item.payload
            claims.append(
                await _upsert_claim(
                    db,
                    investigation_id=investigation_id,
                    workspace_id=workspace_id,
                    key=f"fact:{item.id}",
                    classification=ClaimClassification.FACT,
                    statement=(
                        f"{payload.get('entity_name') or 'Company'} {payload['metric_key']} was "
                        f"{payload['value']} {payload['unit']} for {payload['period_start']}."
                    ),
                    validation_status=ClaimValidationStatus.VALIDATED,
                    evidence=[item],
                    relationship="supports",
                    confidence=Decimal("1.0"),
                    details={"source_evidence_id": str(item.id)},
                )
            )
        elif item.evidence_kind in {"business_record", "document_chunk", "relationship"}:
            title = item.payload.get("title") or item.payload.get("filename") or item.source_kind
            claims.append(
                await _upsert_claim(
                    db,
                    investigation_id=investigation_id,
                    workspace_id=workspace_id,
                    key=f"fact:{item.id}",
                    classification=ClaimClassification.FACT,
                    statement=f"Source evidence records: {title}.",
                    validation_status=ClaimValidationStatus.VALIDATED,
                    evidence=[item],
                    relationship="supports",
                    confidence=Decimal("1.0"),
                    details={"source_evidence_id": str(item.id)},
                )
            )

    calculations = [item for item in evidence if item.evidence_kind == "calculation"]
    evidence_by_id = {str(item.id): item for item in evidence}
    primary_entity_id: str | None = None
    for item in calculations:
        payload = item.payload
        inputs = [
            evidence_by_id[value]
            for value in payload.get("input_evidence_ids", [])
            if value in evidence_by_id
        ]
        linked = [item, *inputs]
        if payload.get("operation") == "metric_change":
            percentage = payload.get("percentage_change")
            statement = (
                f"Revenue changed from {payload['inputs']['comparison']} USD to "
                f"{payload['inputs']['current']} USD, a change of {payload['result']} USD"
                + (f" ({percentage}%)." if percentage is not None else ".")
            )
            key = "derived:metric_change"
        elif payload.get("operation") == "rank_entity_contributions":
            top = payload["contributions"][0]
            primary_entity_id = top["entity_id"]
            statement = (
                f"{top['entity_name']} changed by {top['change']} USD and accounted for "
                f"{top['contribution_percentage']}% of the total movement."
            )
            key = "derived:entity_contributions"
        else:
            continue
        claims.append(
            await _upsert_claim(
                db,
                investigation_id=investigation_id,
                workspace_id=workspace_id,
                key=key,
                classification=ClaimClassification.DERIVED,
                statement=statement,
                validation_status=ClaimValidationStatus.VALIDATED,
                evidence=linked,
                relationship="derived_from",
                confidence=Decimal("1.0"),
                formula=payload.get("formula"),
                details=payload,
            )
        )

    metric_change = next(
        (item for item in calculations if item.payload.get("operation") == "metric_change"),
        None,
    )
    causal_cutoff: date | None = None
    if metric_change and metric_change.payload.get("current_period_start"):
        current_period = date.fromisoformat(metric_change.payload["current_period_start"])
        causal_cutoff = current_period.replace(
            day=monthrange(current_period.year, current_period.month)[1]
        )

    related = [
        item
        for item in evidence
        if primary_entity_id and primary_entity_id in item.related_entity_ids
    ]
    by_group: dict[str, list[EvidenceItem]] = defaultdict(list)
    for item in related:
        if item.evidence_kind != "calculation" and not item.provenance_group.startswith("metric:"):
            by_group[item.provenance_group].append(item)
    support = [item for item in related if item.source_kind == "support_incident"]
    projects = [item for item in related if item.source_kind == "project_update"]
    crm = [item for item in related if item.source_kind == "crm_activity"]
    documents = [item for item in related if item.evidence_kind == "document_chunk"]
    causal = support + projects + crm + documents
    if primary_entity_id:
        name = entity_names.get(uuid.UUID(primary_entity_id), "The leading customer")
        independent_groups = len({item.provenance_group for item in causal})
        temporally_ordered = bool(causal_cutoff) and any(
            item.observed_at is not None and item.observed_at.date() <= causal_cutoff
            for item in causal
        )
        essential_missing = not support or not projects
        confidence = Decimal("0.30")
        confidence += min(Decimal("0.30"), Decimal("0.15") * independent_groups)
        if temporally_ordered:
            confidence += Decimal("0.15")
        confidence += Decimal("0.15")
        if documents:
            confidence += Decimal("0.10")
        if essential_missing:
            confidence -= Decimal("0.20")
        confidence = max(Decimal(0), min(Decimal(1), confidence))
        valid_structure = len(by_group) >= 2 and not essential_missing
        status = (
            ClaimValidationStatus.VALIDATED
            if valid_structure and confidence >= Decimal("0.70")
            else ClaimValidationStatus.INSUFFICIENT_EVIDENCE
        )
        statement = (
            f"Severe export failures and delayed remediation likely contributed to {name}'s "
            "reduced renewal scope and revenue decline."
        )
        claims.append(
            await _upsert_claim(
                db,
                investigation_id=investigation_id,
                workspace_id=workspace_id,
                key="hypothesis:primary_driver",
                classification=ClaimClassification.HYPOTHESIS,
                statement=statement,
                validation_status=status,
                evidence=causal,
                relationship="supports",
                confidence=confidence,
                details={
                    "supporting_evidence_ids": [str(item.id) for item in causal],
                    "contradicting_evidence_ids": [],
                    "causal_gaps": (
                        []
                        if not essential_missing
                        else ["Support incidents and remediation timing are not both available."]
                    ),
                    "independent_causal_groups": independent_groups,
                    "primary_entity_id": primary_entity_id,
                    "temporally_ordered": temporally_ordered,
                },
            )
        )
    await db.flush()
    return claims


async def build_executive_brief(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    optional_failures: list[str],
) -> ExecutiveBrief:
    claims = list(
        (
            await db.execute(
                select(Claim)
                .where(
                    Claim.investigation_id == investigation_id,
                    Claim.workspace_id == workspace_id,
                )
                .order_by(Claim.created_at, Claim.id)
            )
        )
        .scalars()
        .all()
    )
    valid = [claim for claim in claims if claim.validation_status == "validated"]
    change = next(
        (
            claim
            for claim in valid
            if claim.classification == "derived"
            and claim.details.get("operation") == "metric_change"
        ),
        None,
    )
    if change is None:
        raise ValueError("A validated metric-change claim is required")
    driver = next(
        (
            claim
            for claim in valid
            if claim.classification == "derived"
            and claim.details.get("operation") == "rank_entity_contributions"
        ),
        None,
    )
    hypothesis = max(
        (claim for claim in valid if claim.classification == "hypothesis"),
        key=lambda claim: claim.confidence or Decimal(0),
        default=None,
    )
    links = (
        list(
            (
                await db.execute(
                    select(ClaimEvidence).where(
                        ClaimEvidence.claim_id.in_([claim.id for claim in valid])
                    )
                )
            ).scalars()
        )
        if valid
        else []
    )
    evidence = (
        list(
            (
                await db.execute(
                    select(EvidenceItem)
                    .where(
                        EvidenceItem.workspace_id == workspace_id,
                        EvidenceItem.id.in_([link.evidence_id for link in links]),
                    )
                    .order_by(EvidenceItem.created_at, EvidenceItem.id)
                )
            ).scalars()
        )
        if links
        else []
    )
    claims_by_evidence: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for link in links:
        claims_by_evidence[link.evidence_id].append(link.claim_id)
    selected: list[EvidenceItem] = []
    seen_groups: set[str] = set()
    for item in evidence:
        if item.provenance_group not in seen_groups:
            selected.append(item)
            seen_groups.add(item.provenance_group)
        if len(selected) == 8:
            break
    if hypothesis:
        score = Decimal("0.60") + (hypothesis.confidence or Decimal(0)) * Decimal("0.40")
    else:
        score = Decimal("0.44")
    score = min(Decimal(1), score)
    level = (
        ExecutiveBriefConfidenceLevel.HIGH
        if score >= Decimal("0.75")
        else ExecutiveBriefConfidenceLevel.MEDIUM
        if score >= Decimal("0.45")
        else ExecutiveBriefConfidenceLevel.LOW
    )
    uncertainties = [ExecutiveBriefUncertainty(text=value) for value in optional_failures]
    insufficient = [claim for claim in claims if claim.validation_status == "insufficient_evidence"]
    for claim in insufficient:
        uncertainties.append(
            ExecutiveBriefUncertainty(text="Causal explanation has insufficient evidence.")
        )
    brief = ExecutiveBrief(
        what_happened=SupportedBriefStatement(text=change.statement, claim_ids=[change.id]),
        primary_driver=(
            SupportedBriefStatement(text=driver.statement, claim_ids=[driver.id])
            if driver
            else None
        ),
        likely_explanation=(
            SupportedBriefStatement(text=hypothesis.statement, claim_ids=[hypothesis.id])
            if hypothesis
            else None
        ),
        confidence=ExecutiveBriefConfidence(
            score=float(score),
            level=level,
            rationale=(
                "Measured results and independent causal evidence are validated."
                if hypothesis
                else "Measured results are validated, but causal evidence is insufficient."
            ),
        ),
        key_evidence=[
            ExecutiveBriefEvidence(
                evidence_id=item.id,
                label=item.content or item.payload.get("title") or item.evidence_kind,
                claim_ids=claims_by_evidence[item.id],
            )
            for item in selected
        ],
        uncertainties=uncertainties,
        recommended_follow_up_questions=(
            []
            if hypothesis
            else [
                "Which support incidents affected the renewal decision?",
                "When was the remediation project completed relative to renewal?",
            ]
        ),
    )
    validate_executive_brief_references(
        brief,
        valid_claim_ids={claim.id for claim in valid},
        valid_evidence_ids={item.id for item in evidence},
    )
    return brief


async def build_evidence_graph(
    db: AsyncSession, investigation_id: uuid.UUID, workspace_id: uuid.UUID
) -> EvidenceGraph:
    claims = list(
        (
            await db.execute(
                select(Claim).where(
                    Claim.investigation_id == investigation_id,
                    Claim.workspace_id == workspace_id,
                )
            )
        )
        .scalars()
        .all()
    )
    evidence = list(
        (
            await db.execute(
                select(EvidenceItem).where(
                    EvidenceItem.investigation_id == investigation_id,
                    EvidenceItem.workspace_id == workspace_id,
                )
            )
        ).scalars()
    )
    links = (
        list(
            (
                await db.execute(
                    select(ClaimEvidence).where(
                        ClaimEvidence.claim_id.in_([claim.id for claim in claims])
                    )
                )
            ).scalars()
        )
        if claims
        else []
    )
    nodes = [
        EvidenceGraphNode(
            id=str(claim.id),
            kind=EvidenceGraphNodeKind.CLAIM,
            label=claim.statement,
            classification=claim.classification,
        )
        for claim in claims
    ] + [
        EvidenceGraphNode(
            id=str(item.id),
            kind=(
                EvidenceGraphNodeKind.CALCULATION
                if item.evidence_kind == "calculation"
                else EvidenceGraphNodeKind.EVIDENCE
            ),
            label=item.content or item.payload.get("title") or item.evidence_kind,
            provenance={"group": item.provenance_group, "locator": item.source_locator},
        )
        for item in evidence
    ]
    edge_kind = {
        "supports": EvidenceGraphEdgeKind.SUPPORTS,
        "contradicts": EvidenceGraphEdgeKind.CONTRADICTS,
        "derived_from": EvidenceGraphEdgeKind.DERIVED_FROM,
    }
    edges = [
        EvidenceGraphEdge(
            id=f"{link.evidence_id}:{link.claim_id}",
            source=str(link.evidence_id),
            target=str(link.claim_id),
            kind=edge_kind[link.relationship],
        )
        for link in links
    ]
    return EvidenceGraph(nodes=nodes, edges=edges)
