from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.demo.orion_importer import import_orion_company
from app.investigations.orchestrator import InvestigationOrchestrator, mark_failed
from app.models import DEMO_WORKSPACE_ID, Claim, Investigation
from app.services.document_ingestion import DeleteAdapter, UploadAdapter


async def _run_investigation(db: AsyncSession, question: str) -> tuple[Investigation, list[Claim]]:
    investigation = Investigation(
        question=question,
        workspace_id=DEMO_WORKSPACE_ID,
        created_by_subject="demo-evaluation",
    )
    db.add(investigation)
    await db.commit()
    await db.refresh(investigation)
    try:
        await InvestigationOrchestrator(db, deterministic=True).run(investigation.id)
    except Exception as error:
        await mark_failed(db, investigation.id, error)
        raise
    claims = list(
        (
            await db.execute(
                select(Claim)
                .where(Claim.investigation_id == investigation.id)
                .order_by(Claim.created_at, Claim.id)
            )
        )
        .scalars()
        .all()
    )
    return investigation, claims


def _claim(claims: list[Claim], operation: str) -> Claim:
    return next(claim for claim in claims if claim.details.get("operation") == operation)


def _hypothesis(claims: list[Claim]) -> Claim:
    return next(claim for claim in claims if claim.classification == "hypothesis")


async def evaluate_orion_controls(
    db: AsyncSession,
    root: Path,
    *,
    upload: UploadAdapter,
    delete: DeleteAdapter,
    processor: Callable[[bytes, str], Awaitable[dict]],
) -> dict[str, Any]:
    expected = json.loads((root / "expected_findings.json").read_text())
    negative_expected = json.loads((root / "negative_control.json").read_text())

    await import_orion_company(
        db, root, upload=upload, delete=delete, processor=processor, negative_control=False
    )
    positive, positive_claims = await _run_investigation(db, expected["question"])
    change = _claim(positive_claims, "metric_change")
    contributions = _claim(positive_claims, "rank_entity_contributions")
    positive_hypothesis = _hypothesis(positive_claims)
    top = contributions.details["contributions"][0]

    assert change.details["inputs"]["comparison"] == expected["comparison_total"]
    assert change.details["inputs"]["current"] == expected["current_total"]
    assert change.details["result"] == expected["absolute_change"]
    assert change.details["percentage_change"] == expected["percentage_change"]
    assert top["entity_name"] == expected["primary_entity"]
    assert top["change"] == expected["primary_entity_change"]
    assert top["contribution_percentage"] == expected["contribution_percentage"]
    assert positive_hypothesis.validation_status == "validated"
    assert positive_hypothesis.confidence is not None
    assert positive_hypothesis.confidence >= Decimal(str(expected["minimum_hypothesis_confidence"]))

    try:
        await import_orion_company(
            db, root, upload=upload, delete=delete, processor=processor, negative_control=True
        )
        negative, negative_claims = await _run_investigation(db, expected["question"])
        negative_hypothesis = _hypothesis(negative_claims)
        negative_brief = negative.executive_brief or {}
        assert negative_hypothesis.validation_status == "insufficient_evidence"
        assert negative_hypothesis.confidence is not None
        assert negative_hypothesis.confidence < positive_hypothesis.confidence
        assert negative_brief.get("likely_explanation") is negative_expected[
            "expected_likely_explanation"
        ]
        assert Decimal(str(negative_brief["confidence"]["score"])) <= Decimal(
            str(negative_expected["maximum_brief_confidence"])
        )
    finally:
        await import_orion_company(
            db, root, upload=upload, delete=delete, processor=processor, negative_control=False
        )

    return {
        "positive_investigation_id": str(positive.id),
        "positive_hypothesis_confidence": str(positive_hypothesis.confidence),
        "negative_investigation_id": str(negative.id),
        "negative_hypothesis_confidence": str(negative_hypothesis.confidence),
        "negative_brief_confidence": negative_brief["confidence"]["score"],
    }
