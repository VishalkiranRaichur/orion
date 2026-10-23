from __future__ import annotations

import csv
import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DEMO_DATA_SOURCE_ID,
    DEMO_WORKSPACE_ID,
    BusinessRecord,
    DataSource,
    Document,
    Entity,
    EntityRelationship,
    MetricObservation,
    Workspace,
)
from app.services.document_ingestion import DeleteAdapter, UploadAdapter, ingest_document

DEMO_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "orion:demo:company")


def demo_id(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(DEMO_NAMESPACE, f"{kind}:{key}")


class DemoRow(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CustomerRow(DemoRow):
    customer_id: str
    name: str
    segment: str


class RevenueRow(DemoRow):
    customer_id: str
    period_start: date
    period_end: date
    recognized_revenue_usd: Decimal
    currency: str

    @field_validator("currency")
    @classmethod
    def usd_only(cls, value: str) -> str:
        if value != "USD":
            raise ValueError("Only USD revenue is supported by the demo")
        return value


class ActivityRow(DemoRow):
    activity_id: str
    customer_id: str
    occurred_at: datetime
    title: str
    content: str


class IncidentRow(DemoRow):
    incident_id: str
    customer_id: str
    occurred_at: datetime
    severity: str
    title: str
    content: str


class ProjectRow(DemoRow):
    project_id: str
    customer_id: str
    name: str
    planned_date: date
    actual_date: date
    status: str
    content: str


class ContractRow(DemoRow):
    contract_id: str
    customer_id: str
    renewal_date: date
    previous_value_usd: Decimal
    renewed_value_usd: Decimal
    currency: str
    document: str

    @field_validator("currency")
    @classmethod
    def usd_only(cls, value: str) -> str:
        if value != "USD":
            raise ValueError("Only USD contracts are supported by the demo")
        return value


def _read_rows(path: Path, row_type: type[DemoRow]) -> list[DemoRow]:
    with path.open(newline="", encoding="utf-8") as stream:
        return [row_type.model_validate(row) for row in csv.DictReader(stream)]


async def _put(db: AsyncSession, model_type, identifier: uuid.UUID, **values):
    value = await db.get(model_type, identifier)
    if value is None:
        value = model_type(id=identifier, **values)
        db.add(value)
    else:
        expected_workspace = values.get("workspace_id")
        if expected_workspace is not None and value.workspace_id != expected_workspace:
            raise ValueError("A deterministic demo ID is already used outside the demo workspace")
        for key, item in values.items():
            setattr(value, key, item)
    return value


async def import_orion_company(
    db: AsyncSession,
    root: Path,
    *,
    upload: UploadAdapter,
    delete: DeleteAdapter,
    processor: Callable[[bytes, str], Awaitable[dict]],
    negative_control: bool = False,
) -> dict[str, int]:
    await _put(
        db,
        Workspace,
        DEMO_WORKSPACE_ID,
        name="ORION Demo Company",
        industry="Software",
        owner_subject=None,
        is_demo=True,
    )
    await db.flush()
    demo_source = await _put(
        db,
        DataSource,
        DEMO_DATA_SOURCE_ID,
        workspace_id=DEMO_WORKSPACE_ID,
        name="ORION Demo Import",
        source_type="demo",
        status="ready",
        external_key="demo:orion_company",
        error=None,
    )
    await db.flush()
    customers = _read_rows(root / "customers.csv", CustomerRow)
    revenue = _read_rows(root / "revenue.csv", RevenueRow)
    crm = _read_rows(root / "crm_activity.csv", ActivityRow)
    incidents = _read_rows(root / "support_incidents.csv", IncidentRow)
    projects = _read_rows(root / "projects.csv", ProjectRow)
    contracts = _read_rows(root / "contracts.csv", ContractRow)
    customer_keys = {row.customer_id for row in customers}
    for collection in (revenue, crm, incidents, projects, contracts):
        unknown = {row.customer_id for row in collection} - customer_keys
        if unknown:
            raise ValueError(f"Rows reference unknown customers: {sorted(unknown)}")
    for row in revenue:
        if row.period_start > row.period_end:
            raise ValueError("Revenue period_start must not be after period_end")
    manifest = (
        json.loads((root / "negative_control.json").read_text())
        if negative_control
        else {"exclude_support_incidents": [], "exclude_projects": []}
    )
    excluded_incidents = set(manifest.get("exclude_support_incidents", []))
    excluded_projects = set(manifest.get("exclude_projects", []))

    if negative_control:
        excluded_record_ids = [
            demo_id("record", f"support_incident:{incident_id}")
            for incident_id in excluded_incidents
        ] + [demo_id("record", f"project_update:{project_id}") for project_id in excluded_projects]
        if excluded_record_ids:
            await db.execute(
                sa_delete(BusinessRecord)
                .where(BusinessRecord.id.in_(excluded_record_ids))
                .where(BusinessRecord.workspace_id == DEMO_WORKSPACE_ID)
            )
        excluded_project_rows = [row for row in projects if row.project_id in excluded_projects]
        excluded_relationship_ids = [
            demo_id("relationship", f"{row.customer_id}:project:{row.project_id}")
            for row in excluded_project_rows
        ]
        if excluded_relationship_ids:
            await db.execute(
                sa_delete(EntityRelationship).where(
                    EntityRelationship.workspace_id == DEMO_WORKSPACE_ID,
                    EntityRelationship.id.in_(excluded_relationship_ids),
                )
            )
        excluded_entity_ids = [demo_id("project", row.project_id) for row in excluded_project_rows]
        if excluded_entity_ids:
            await db.execute(
                sa_delete(Entity).where(
                    Entity.workspace_id == DEMO_WORKSPACE_ID,
                    Entity.id.in_(excluded_entity_ids),
                )
            )

    entities: dict[str, Entity] = {}
    for row in customers:
        entities[row.customer_id] = await _put(
            db,
            Entity,
            demo_id("customer", row.customer_id),
            workspace_id=DEMO_WORKSPACE_ID,
            entity_type="customer",
            external_key=f"demo:{row.customer_id}",
            name=row.name,
            attributes={"segment": row.segment, "demo": True},
        )
    await db.flush()

    documents: dict[str, Document] = {}
    document_paths = sorted((root / "contracts").glob("*.md")) + sorted(
        (root / "meeting_notes").glob("*.md")
    )
    for path in document_paths:
        relative = str(path.relative_to(root))
        identifier = demo_id("document", relative)
        existing = await db.get(Document, identifier)
        if existing is None:
            existing = await ingest_document(
                db=db,
                workspace_id=DEMO_WORKSPACE_ID,
                file_bytes=path.read_bytes(),
                filename=path.name,
                content_type="text/markdown",
                storage_key=f"demo/orion_company/{relative}",
                upload=upload,
                delete=delete,
                processor=processor,
                document_id=identifier,
                data_source_id=DEMO_DATA_SOURCE_ID,
                commit=False,
            )
        elif existing.workspace_id != DEMO_WORKSPACE_ID:
            raise ValueError("A deterministic demo document ID is used outside the demo workspace")
        else:
            existing.data_source_id = DEMO_DATA_SOURCE_ID
        documents[relative] = existing

    for row_number, row in enumerate(revenue, start=2):
        await _put(
            db,
            MetricObservation,
            demo_id("observation", f"{row.customer_id}:{row.period_start}"),
            workspace_id=DEMO_WORKSPACE_ID,
            metric_key="recognized_revenue_usd",
            entity_id=entities[row.customer_id].id,
            period_start=row.period_start,
            period_end=row.period_end,
            value=row.recognized_revenue_usd,
            unit=row.currency,
            dimensions={"customer_id": row.customer_id, "demo": True},
            source_document_id=None,
            source_locator={"file": "revenue.csv", "row": row_number},
        )

    async def record(
        record_type: str,
        external_key: str,
        customer_id: str,
        occurred_at: datetime,
        title: str,
        content: str,
        attributes: dict,
        source_file: str,
        row_number: int,
        related_entity_id: uuid.UUID | None = None,
        source_document_id: uuid.UUID | None = None,
    ) -> None:
        await _put(
            db,
            BusinessRecord,
            demo_id("record", f"{record_type}:{external_key}"),
            workspace_id=DEMO_WORKSPACE_ID,
            record_type=record_type,
            external_key=f"demo:{external_key}",
            primary_entity_id=entities[customer_id].id,
            related_entity_id=related_entity_id,
            occurred_at=occurred_at,
            title=title,
            content=content,
            attributes={**attributes, "demo": True},
            source_document_id=source_document_id,
            source_locator={"file": source_file, "row": row_number},
        )

    for index, row in enumerate(crm, start=2):
        await record(
            "crm_activity",
            row.activity_id,
            row.customer_id,
            row.occurred_at,
            row.title,
            row.content,
            {},
            "crm_activity.csv",
            index,
        )
    for index, row in enumerate(incidents, start=2):
        if row.incident_id in excluded_incidents:
            continue
        await record(
            "support_incident",
            row.incident_id,
            row.customer_id,
            row.occurred_at,
            row.title,
            row.content,
            {"severity": row.severity},
            "support_incidents.csv",
            index,
        )
    for index, row in enumerate(projects, start=2):
        if row.project_id in excluded_projects:
            continue
        project = await _put(
            db,
            Entity,
            demo_id("project", row.project_id),
            workspace_id=DEMO_WORKSPACE_ID,
            entity_type="project",
            external_key=f"demo:{row.project_id}",
            name=row.name,
            attributes={"status": row.status, "demo": True},
        )
        await _put(
            db,
            EntityRelationship,
            demo_id("relationship", f"{row.customer_id}:project:{row.project_id}"),
            workspace_id=DEMO_WORKSPACE_ID,
            source_entity_id=entities[row.customer_id].id,
            target_entity_id=project.id,
            relationship_type="has_project",
            valid_from=row.planned_date,
            valid_to=None,
            attributes={"demo": True},
            source_document_id=None,
        )
        await record(
            "project_update",
            row.project_id,
            row.customer_id,
            datetime.combine(row.actual_date, datetime.min.time(), tzinfo=UTC),
            row.name,
            row.content,
            {
                "planned_date": row.planned_date.isoformat(),
                "actual_date": row.actual_date.isoformat(),
                "status": row.status,
            },
            "projects.csv",
            index,
            related_entity_id=project.id,
        )
    for index, row in enumerate(contracts, start=2):
        contract = await _put(
            db,
            Entity,
            demo_id("contract", row.contract_id),
            workspace_id=DEMO_WORKSPACE_ID,
            entity_type="contract",
            external_key=f"demo:{row.contract_id}",
            name=f"{entities[row.customer_id].name} contract",
            attributes={"demo": True},
        )
        document = documents[row.document]
        await _put(
            db,
            EntityRelationship,
            demo_id("relationship", f"{row.customer_id}:contract:{row.contract_id}"),
            workspace_id=DEMO_WORKSPACE_ID,
            source_entity_id=entities[row.customer_id].id,
            target_entity_id=contract.id,
            relationship_type="has_contract",
            valid_from=row.renewal_date,
            valid_to=None,
            attributes={"demo": True},
            source_document_id=document.id,
        )
        await record(
            "renewal_event",
            row.contract_id,
            row.customer_id,
            datetime.combine(row.renewal_date, datetime.min.time(), tzinfo=UTC),
            "Contract renewal",
            "Contract renewed at a reduced value; the contract does not state a cause.",
            {
                "previous_value_usd": str(row.previous_value_usd),
                "renewed_value_usd": str(row.renewed_value_usd),
                "currency": row.currency,
            },
            "contracts.csv",
            index,
            related_entity_id=contract.id,
            source_document_id=document.id,
        )

    meeting_relative = "meeting_notes/northstar_renewal.md"
    meeting_document = documents.get(meeting_relative)
    if meeting_document:
        await record(
            "crm_activity",
            "northstar-renewal-meeting",
            "northstar",
            datetime(2026, 6, 25, tzinfo=UTC),
            "Northstar renewal meeting",
            "The customer raised renewal concern while export reliability remained unresolved.",
            {"source": "meeting_note"},
            meeting_relative,
            1,
            source_document_id=meeting_document.id,
        )
    demo_source.status = "ready"
    demo_source.error = None
    demo_source.last_synced_at = datetime.now(UTC)
    await db.commit()
    return {
        "customers": len(customers),
        "revenue_observations": len(revenue),
        "business_records": len(crm)
        + len([row for row in incidents if row.incident_id not in excluded_incidents])
        + len([row for row in projects if row.project_id not in excluded_projects])
        + len(contracts)
        + 1,
        "documents": len(documents),
    }
