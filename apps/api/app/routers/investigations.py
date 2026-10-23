from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime

from celery import Celery
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, get_current_principal
from app.config import settings
from app.db import get_db
from app.investigations.claims import build_evidence_graph
from app.models import (
    Claim,
    ClaimEvidence,
    EvidenceItem,
    Investigation,
    InvestigationStep,
    Workspace,
)
from app.schemas.investigation import (
    ExecutiveBrief,
    ExecutiveBriefConfidenceLevel,
    InvestigationCreatedResponse,
    InvestigationCreateRequest,
    InvestigationDetailResponse,
    InvestigationHistoryItem,
    InvestigationHistoryResponse,
)
from app.workspaces import get_active_workspace

router = APIRouter()
celery_client = Celery("orion-api", broker=settings.celery_broker_url)


def _brief_confidence(
    brief_payload: dict | None,
) -> tuple[float | None, ExecutiveBriefConfidenceLevel | None]:
    if not brief_payload:
        return None, None
    try:
        brief = ExecutiveBrief.model_validate(brief_payload)
    except ValueError:
        return None, None
    return brief.confidence.score, brief.confidence.level


def _step_metadata(
    plan_payload: dict | None, sequence: int, tool: str
) -> tuple[str, bool, list[int]]:
    plan_steps = plan_payload.get("steps", []) if isinstance(plan_payload, dict) else []
    for item in plan_steps:
        if isinstance(item, dict) and item.get("sequence") == sequence:
            description = item.get("description")
            depends_on = item.get("depends_on", [])
            return (
                (
                    description
                    if isinstance(description, str) and description
                    else tool.replace("_", " ").title()
                ),
                item.get("required") is not False,
                [value for value in depends_on if isinstance(value, int)]
                if isinstance(depends_on, list)
                else [],
            )
    return tool.replace("_", " ").title(), True, []


def _encode_cursor(created_at: datetime, investigation_id: uuid.UUID) -> str:
    value = json.dumps([created_at.isoformat(), str(investigation_id)]).encode()
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = value + "=" * (-len(value) % 4)
        created_at, investigation_id = json.loads(
            base64.urlsafe_b64decode(padded.encode()).decode()
        )
        return datetime.fromisoformat(created_at), uuid.UUID(investigation_id)
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail="Invalid pagination cursor.") from error


@router.post(
    "",
    response_model=InvestigationCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_investigation(
    request: InvestigationCreateRequest,
    workspace: Workspace = Depends(get_active_workspace),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Investigation:
    if not settings.investigations_enabled:
        raise HTTPException(status_code=503, detail="Investigations are disabled.")
    investigation = Investigation(
        question=request.question.strip(),
        workspace_id=workspace.id,
        created_by_subject=principal.subject,
    )
    db.add(investigation)
    await db.commit()
    await db.refresh(investigation)
    try:
        await run_in_threadpool(
            celery_client.send_task,
            "orion.run_investigation",
            args=[str(investigation.id)],
            task_id=str(investigation.id),
            queue="investigations",
        )
    except Exception as error:
        investigation.status = "failed"
        investigation.failure_code = "enqueue_failed"
        investigation.error = "The investigation could not be queued."
        investigation.completed_at = datetime.now(UTC)
        investigation.updated_at = investigation.completed_at
        await db.commit()
        raise HTTPException(
            status_code=503,
            detail={
                "message": "The investigation could not be queued.",
                "investigation_id": str(investigation.id),
            },
        ) from error
    return investigation


@router.get("", response_model=InvestigationHistoryResponse)
async def list_investigations(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    workspace: Workspace = Depends(get_active_workspace),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> InvestigationHistoryResponse:
    statement = select(Investigation).where(Investigation.workspace_id == workspace.id)
    if workspace.is_demo:
        statement = statement.where(Investigation.created_by_subject == principal.subject)
    if cursor:
        created_at, investigation_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                Investigation.created_at < created_at,
                and_(
                    Investigation.created_at == created_at,
                    Investigation.id < investigation_id,
                ),
            )
        )
    rows = list(
        (
            await db.execute(
                statement.order_by(Investigation.created_at.desc(), Investigation.id.desc()).limit(
                    limit + 1
                )
            )
        )
        .scalars()
        .all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = []
    for item in rows:
        confidence_score, confidence_level = _brief_confidence(item.executive_brief)
        items.append(
            InvestigationHistoryItem(
                id=item.id,
                question=item.question,
                status=item.status,
                created_at=item.created_at,
                updated_at=item.updated_at,
                started_at=item.started_at,
                completed_at=item.completed_at,
                intent_summary=item.intent.get("kind") if item.intent else None,
                brief_preview=item.summary,
                confidence_score=confidence_score,
                confidence_level=confidence_level,
            )
        )
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if has_more else None
    return InvestigationHistoryResponse(items=items, next_cursor=next_cursor)


@router.get("/{investigation_id}", response_model=InvestigationDetailResponse)
async def get_investigation(
    investigation_id: uuid.UUID,
    workspace: Workspace = Depends(get_active_workspace),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> InvestigationDetailResponse:
    filters = [
        Investigation.id == investigation_id,
        Investigation.workspace_id == workspace.id,
    ]
    if workspace.is_demo:
        filters.append(Investigation.created_by_subject == principal.subject)
    investigation = (await db.execute(select(Investigation).where(*filters))).scalar_one_or_none()
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    steps = list(
        (
            await db.execute(
                select(InvestigationStep)
                .where(
                    InvestigationStep.investigation_id == investigation_id,
                    InvestigationStep.workspace_id == workspace.id,
                )
                .order_by(InvestigationStep.sequence)
            )
        )
        .scalars()
        .all()
    )
    evidence = list(
        (
            await db.execute(
                select(EvidenceItem)
                .where(
                    EvidenceItem.investigation_id == investigation_id,
                    EvidenceItem.workspace_id == workspace.id,
                )
                .order_by(EvidenceItem.created_at, EvidenceItem.id)
            )
        )
        .scalars()
        .all()
    )
    claims = list(
        (
            await db.execute(
                select(Claim)
                .where(
                    Claim.investigation_id == investigation_id,
                    Claim.workspace_id == workspace.id,
                )
                .order_by(Claim.created_at, Claim.id)
            )
        )
        .scalars()
        .all()
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
    evidence_by_claim: dict[uuid.UUID, list[uuid.UUID]] = {}
    for link in links:
        evidence_by_claim.setdefault(link.claim_id, []).append(link.evidence_id)
    graph = await build_evidence_graph(db, investigation_id, workspace.id)
    step_responses = []
    for step in steps:
        description, required, depends_on = _step_metadata(
            investigation.plan, step.sequence, step.tool
        )
        step_responses.append(
            {
                "sequence": step.sequence,
                "tool": step.tool,
                "description": description,
                "required": required,
                "depends_on": depends_on,
                "status": step.status,
                "input": step.input,
                "output": step.output,
                "error": step.error,
                "started_at": step.started_at,
                "completed_at": step.completed_at,
            }
        )
    return InvestigationDetailResponse(
        id=investigation.id,
        question=investigation.question,
        status=investigation.status,
        created_at=investigation.created_at,
        updated_at=investigation.updated_at,
        started_at=investigation.started_at,
        completed_at=investigation.completed_at,
        failure_code=investigation.failure_code,
        error=investigation.error,
        intent=investigation.intent,
        assumptions=investigation.assumptions,
        plan=investigation.plan,
        execution_usage=investigation.execution_usage,
        steps=step_responses,
        claims=[
            {
                "id": claim.id,
                "classification": claim.classification,
                "statement": claim.statement,
                "confidence": float(claim.confidence) if claim.confidence is not None else None,
                "formula": claim.formula,
                "details": claim.details,
                "validation_status": claim.validation_status,
                "evidence_ids": evidence_by_claim.get(claim.id, []),
            }
            for claim in claims
        ],
        evidence=[
            {
                "id": item.id,
                "step_id": item.step_id,
                "evidence_kind": item.evidence_kind,
                "source_kind": item.source_kind,
                "source_id": item.source_id,
                "provenance_group": item.provenance_group,
                "source_locator": item.source_locator,
                "related_entity_ids": item.related_entity_ids,
                "content": item.content,
                "payload": item.payload,
                "observed_at": item.observed_at,
            }
            for item in evidence
        ],
        executive_brief=(
            ExecutiveBrief.model_validate(investigation.executive_brief)
            if investigation.executive_brief
            else None
        ),
        evidence_graph=graph,
    )
