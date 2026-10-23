from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.investigations.budget import ExecutionBudget
from app.investigations.errors import RequiredDataError, ToolExecutionError
from app.models import (
    BusinessRecord,
    Entity,
    EntityRelationship,
    EvidenceItem,
    InvestigationStep,
    MetricObservation,
)
from app.schemas.investigation import (
    CalculateMetricChangeInput,
    InvestigationToolCall,
    InvestigationToolKind,
    QueryMetricSeriesInput,
    QueryRelatedRecordsInput,
    RankEntityContributionsInput,
    SemanticDocumentSearchInput,
    TraverseRelationshipsInput,
)
from app.services.search_service import semantic_search

EVIDENCE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "orion:evidence")


def decimal_string(value: Decimal) -> str:
    formatted = format(value, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted or "0"


class ToolExecutor:
    def __init__(
        self,
        db: AsyncSession,
        investigation_id: uuid.UUID,
        workspace_id: uuid.UUID,
        budget: ExecutionBudget,
    ):
        self.db = db
        self.investigation_id = investigation_id
        self.workspace_id = workspace_id
        self.budget = budget
        self.prior_outputs: dict[int, dict[str, Any]] = {}

    async def execute(
        self, step: InvestigationStep, tool_call: InvestigationToolCall
    ) -> dict[str, Any]:
        handlers = {
            InvestigationToolKind.QUERY_METRIC_SERIES: self._query_metric_series,
            InvestigationToolKind.CALCULATE_METRIC_CHANGE: self._calculate_metric_change,
            InvestigationToolKind.RANK_ENTITY_CONTRIBUTIONS: self._rank_entity_contributions,
            InvestigationToolKind.QUERY_RELATED_RECORDS: self._query_related_records,
            InvestigationToolKind.SEMANTIC_DOCUMENT_SEARCH: self._semantic_document_search,
            InvestigationToolKind.TRAVERSE_RELATIONSHIPS: self._traverse_relationships,
        }
        handler = handlers.get(tool_call.tool)
        if handler is None:
            raise ToolExecutionError(f"Tool is not enabled for INVESTIGATE: {tool_call.tool}")
        result = await handler(step, tool_call.arguments)
        result["workspace_id"] = str(self.workspace_id)
        self.prior_outputs[step.sequence] = result
        return result

    def load_completed_output(self, sequence: int, output: dict[str, Any]) -> None:
        if output.get("workspace_id") != str(self.workspace_id):
            raise RequiredDataError(
                f"Completed output from step {sequence} is missing trusted workspace scope"
            )
        self.prior_outputs[sequence] = output

    async def _evidence(
        self,
        *,
        step: InvestigationStep,
        kind: str,
        source_kind: str,
        source_id: str,
        provenance_group: str,
        payload: dict[str, Any],
        content: str | None = None,
        source_locator: dict[str, Any] | None = None,
        related_entity_ids: list[uuid.UUID] | None = None,
        observed_at: datetime | None = None,
    ) -> EvidenceItem:
        key = f"{self.investigation_id}:{step.sequence}:{kind}:{source_id}"
        evidence_id = uuid.uuid5(EVIDENCE_NAMESPACE, key)
        existing = await self.db.get(EvidenceItem, evidence_id)
        if existing is not None:
            if existing.workspace_id != self.workspace_id:
                raise ToolExecutionError("Evidence ID collision crossed a workspace boundary")
            return existing
        item = EvidenceItem(
            id=evidence_id,
            workspace_id=self.workspace_id,
            investigation_id=self.investigation_id,
            step_id=step.id,
            evidence_kind=kind,
            source_kind=source_kind,
            source_id=source_id,
            provenance_group=provenance_group,
            source_locator=source_locator or {},
            related_entity_ids=[str(value) for value in related_entity_ids or []],
            content=content,
            payload=payload,
            observed_at=observed_at,
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def _query_metric_series(
        self, step: InvestigationStep, arguments: QueryMetricSeriesInput
    ) -> dict[str, Any]:
        self.budget.consume_retrieval()
        filters = [
            MetricObservation.workspace_id == self.workspace_id,
            MetricObservation.metric_key == arguments.metric_key,
            MetricObservation.period_start >= arguments.period_start,
            MetricObservation.period_end <= arguments.period_end,
        ]
        if arguments.entity_ids:
            await self._validate_entity_ids(arguments.entity_ids)
            filters.append(MetricObservation.entity_id.in_(arguments.entity_ids))
        statement = (
            select(MetricObservation, Entity.name)
            .outerjoin(Entity, Entity.id == MetricObservation.entity_id)
            .where(*filters)
            .order_by(MetricObservation.period_start, Entity.name)
            .limit(100)
        )
        rows = (await self.db.execute(statement)).all()
        if not rows:
            raise RequiredDataError(f"No observations found for {arguments.metric_key}")
        observations = []
        for observation, entity_name in rows:
            payload = {
                "observation_id": str(observation.id),
                "metric_key": observation.metric_key,
                "entity_id": str(observation.entity_id) if observation.entity_id else None,
                "entity_name": entity_name,
                "period_start": observation.period_start.isoformat(),
                "period_end": observation.period_end.isoformat(),
                "value": decimal_string(observation.value),
                "unit": observation.unit,
            }
            evidence = await self._evidence(
                step=step,
                kind="metric_observation",
                source_kind="metric_observation",
                source_id=str(observation.id),
                provenance_group=f"metric:{observation.metric_key}",
                payload=payload,
                source_locator=observation.source_locator,
                related_entity_ids=[observation.entity_id] if observation.entity_id else [],
            )
            observations.append({**payload, "evidence_id": str(evidence.id)})
        return {
            "observations": observations,
            "evidence_ids": [row["evidence_id"] for row in observations],
        }

    def _metric_output(self, sequence: int) -> list[dict[str, Any]]:
        output = self.prior_outputs.get(sequence)
        if (
            not output
            or output.get("workspace_id") != str(self.workspace_id)
            or not output.get("observations")
        ):
            raise RequiredDataError(f"Metric evidence from step {sequence} is unavailable")
        return output["observations"]

    async def _calculate_metric_change(
        self, step: InvestigationStep, arguments: CalculateMetricChangeInput
    ) -> dict[str, Any]:
        observations = self._metric_output(arguments.current_step)
        if arguments.comparison_step:
            observations += self._metric_output(arguments.comparison_step)
        current_key = (
            arguments.current_period_start.isoformat() if arguments.current_period_start else None
        )
        comparison_key = (
            arguments.comparison_period_start.isoformat()
            if arguments.comparison_period_start
            else None
        )
        periods = sorted({row["period_start"] for row in observations})
        if current_key is None or comparison_key is None:
            if len(periods) < 2:
                raise RequiredDataError("Two periods are required to calculate metric change")
            comparison_key, current_key = periods[-2:]
        current_rows = [row for row in observations if row["period_start"] == current_key]
        comparison_rows = [row for row in observations if row["period_start"] == comparison_key]
        if not current_rows or not comparison_rows:
            raise RequiredDataError("Current and comparison observations are required")
        current = sum((Decimal(row["value"]) for row in current_rows), Decimal(0))
        comparison = sum((Decimal(row["value"]) for row in comparison_rows), Decimal(0))
        change = current - comparison
        percentage = None if comparison == 0 else (change / comparison) * Decimal(100)
        input_ids = [row["evidence_id"] for row in comparison_rows + current_rows]
        payload = {
            "operation": "metric_change",
            "formula": "current - comparison; (current - comparison) / comparison * 100",
            "inputs": {
                "current": decimal_string(current),
                "comparison": decimal_string(comparison),
            },
            "result": decimal_string(change),
            "percentage_change": decimal_string(percentage) if percentage is not None else None,
            "input_evidence_ids": input_ids,
            "current_period_start": current_key,
            "comparison_period_start": comparison_key,
        }
        evidence = await self._evidence(
            step=step,
            kind="calculation",
            source_kind="calculation",
            source_id="metric-change",
            provenance_group="calculation:metric_change",
            payload=payload,
        )
        return {**payload, "evidence_ids": [str(evidence.id)]}

    async def _rank_entity_contributions(
        self, step: InvestigationStep, arguments: RankEntityContributionsInput
    ) -> dict[str, Any]:
        observations = self._metric_output(arguments.metric_step)
        current_key = arguments.current_period_start.isoformat()
        comparison_key = arguments.comparison_period_start.isoformat()
        grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for row in observations:
            if row["entity_id"] and row["period_start"] in {current_key, comparison_key}:
                grouped[row["entity_id"]][row["period_start"]] = row
        contributions = []
        total_change = Decimal(0)
        for entity_id, periods in grouped.items():
            if current_key not in periods or comparison_key not in periods:
                continue
            current_row = periods[current_key]
            comparison_row = periods[comparison_key]
            change = Decimal(current_row["value"]) - Decimal(comparison_row["value"])
            total_change += change
            contributions.append(
                {
                    "entity_id": entity_id,
                    "entity_name": current_row["entity_name"],
                    "comparison_value": comparison_row["value"],
                    "current_value": current_row["value"],
                    "change": decimal_string(change),
                    "input_evidence_ids": [
                        comparison_row["evidence_id"],
                        current_row["evidence_id"],
                    ],
                }
            )
        if not contributions:
            raise RequiredDataError("Entity observations are required for contribution ranking")
        for contribution in contributions:
            value = Decimal(contribution["change"])
            percentage = None if total_change == 0 else value / total_change * Decimal(100)
            contribution["contribution_percentage"] = (
                decimal_string(percentage.quantize(Decimal("0.0001")))
                if percentage is not None
                else None
            )
        contributions.sort(key=lambda row: Decimal(row["change"]))
        contributions = contributions[: arguments.limit]
        payload = {
            "operation": "rank_entity_contributions",
            "formula": "entity change / total change * 100",
            "total_change": decimal_string(total_change),
            "contributions": contributions,
            "input_evidence_ids": sorted(
                {value for row in contributions for value in row["input_evidence_ids"]}
            ),
        }
        evidence = await self._evidence(
            step=step,
            kind="calculation",
            source_kind="calculation",
            source_id="entity-contributions",
            provenance_group="calculation:entity_contributions",
            payload=payload,
            related_entity_ids=[uuid.UUID(row["entity_id"]) for row in contributions],
        )
        return {**payload, "evidence_ids": [str(evidence.id)]}

    async def _validate_entity_ids(self, entity_ids: list[uuid.UUID]) -> None:
        if not entity_ids:
            return
        found = set(
            (
                await self.db.execute(
                    select(Entity.id).where(
                        Entity.workspace_id == self.workspace_id,
                        Entity.id.in_(entity_ids),
                    )
                )
            ).scalars()
        )
        if found != set(entity_ids):
            raise RequiredDataError("One or more entities are not available in this workspace")

    async def _resolve_entities(
        self, entity_ids: list[uuid.UUID], selector: Any
    ) -> list[uuid.UUID]:
        if entity_ids:
            await self._validate_entity_ids(entity_ids)
            return entity_ids
        if selector and str(selector) in {
            "top_contributor",
            "DynamicEntitySelector.TOP_CONTRIBUTOR",
        }:
            rankings = [
                output for output in self.prior_outputs.values() if output.get("contributions")
            ]
            if rankings and rankings[-1]["contributions"]:
                return [uuid.UUID(rankings[-1]["contributions"][0]["entity_id"])]
        raise RequiredDataError("Dynamic entity selector could not be resolved")

    async def _query_related_records(
        self, step: InvestigationStep, arguments: QueryRelatedRecordsInput
    ) -> dict[str, Any]:
        self.budget.consume_retrieval()
        entity_ids = await self._resolve_entities(arguments.entity_ids, arguments.entity_selector)
        filters = [
            BusinessRecord.workspace_id == self.workspace_id,
            or_(
                BusinessRecord.primary_entity_id.in_(entity_ids),
                BusinessRecord.related_entity_id.in_(entity_ids),
            ),
        ]
        if arguments.record_types:
            filters.append(
                BusinessRecord.record_type.in_([value.value for value in arguments.record_types])
            )
        if arguments.start:
            filters.append(BusinessRecord.occurred_at >= arguments.start)
        if arguments.end:
            filters.append(BusinessRecord.occurred_at <= arguments.end)
        records = list(
            (
                await self.db.execute(
                    select(BusinessRecord)
                    .where(*filters)
                    .order_by(BusinessRecord.occurred_at)
                    .limit(arguments.limit)
                )
            )
            .scalars()
            .all()
        )
        output = []
        for record in records:
            related = [record.primary_entity_id]
            if record.related_entity_id:
                related.append(record.related_entity_id)
            payload = {
                "record_id": str(record.id),
                "record_type": record.record_type,
                "title": record.title,
                "content": record.content,
                "occurred_at": record.occurred_at.isoformat(),
                "attributes": record.attributes,
                "source_document_id": (
                    str(record.source_document_id) if record.source_document_id else None
                ),
            }
            evidence = await self._evidence(
                step=step,
                kind="business_record",
                source_kind=record.record_type,
                source_id=str(record.id),
                provenance_group=f"record:{record.record_type}",
                payload=payload,
                content=record.content,
                source_locator=record.source_locator,
                related_entity_ids=related,
                observed_at=record.occurred_at,
            )
            output.append({**payload, "evidence_id": str(evidence.id)})
        return {"records": output, "evidence_ids": [row["evidence_id"] for row in output]}

    async def _semantic_document_search(
        self, step: InvestigationStep, arguments: SemanticDocumentSearchInput
    ) -> dict[str, Any]:
        self.budget.consume_retrieval()
        entity_ids = (
            await self._resolve_entities(arguments.entity_ids, arguments.entity_selector)
            if arguments.entity_ids or arguments.entity_selector
            else []
        )
        document_ids = list(arguments.document_ids)
        if entity_ids and not document_ids:
            document_ids = list(
                (
                    await self.db.execute(
                        select(BusinessRecord.source_document_id)
                        .where(
                            BusinessRecord.workspace_id == self.workspace_id,
                            or_(
                                BusinessRecord.primary_entity_id.in_(entity_ids),
                                BusinessRecord.related_entity_id.in_(entity_ids),
                            ),
                            BusinessRecord.source_document_id.is_not(None),
                        )
                        .distinct()
                    )
                ).scalars()
            )
            if not document_ids:
                return {"chunks": [], "evidence_ids": []}
        chunks = await semantic_search(
            self.db,
            self.workspace_id,
            arguments.query,
            limit=arguments.limit,
            document_ids=document_ids or None,
        )
        output = []
        for chunk in chunks:
            payload = {
                "chunk_id": str(chunk.id),
                "document_id": str(chunk.document_id),
                "filename": chunk.document.filename,
                "chunk_index": chunk.chunk_index,
                "excerpt": chunk.content,
            }
            evidence = await self._evidence(
                step=step,
                kind="document_chunk",
                source_kind="document",
                source_id=str(chunk.id),
                provenance_group=f"document:{chunk.document_id}",
                payload=payload,
                content=chunk.content,
                source_locator={
                    "document_id": str(chunk.document_id),
                    "chunk_index": chunk.chunk_index,
                    "filename": chunk.document.filename,
                },
                related_entity_ids=entity_ids,
            )
            output.append({**payload, "evidence_id": str(evidence.id)})
        return {"chunks": output, "evidence_ids": [row["evidence_id"] for row in output]}

    async def _traverse_relationships(
        self, step: InvestigationStep, arguments: TraverseRelationshipsInput
    ) -> dict[str, Any]:
        self.budget.consume_retrieval()
        initial = await self._resolve_entities(arguments.entity_ids, arguments.entity_selector)
        visited = set(initial)
        frontier = set(initial)
        found: dict[uuid.UUID, EntityRelationship] = {}
        for _ in range(arguments.depth):
            if not frontier or len(visited) >= arguments.max_nodes:
                break
            filters = [
                EntityRelationship.workspace_id == self.workspace_id,
                or_(
                    EntityRelationship.source_entity_id.in_(frontier),
                    EntityRelationship.target_entity_id.in_(frontier),
                ),
            ]
            if arguments.relationship_types:
                filters.append(
                    EntityRelationship.relationship_type.in_(arguments.relationship_types)
                )
            relationships = list(
                (await self.db.execute(select(EntityRelationship).where(and_(*filters))))
                .scalars()
                .all()
            )
            next_frontier: set[uuid.UUID] = set()
            for relationship in relationships:
                found[relationship.id] = relationship
                next_frontier.update({relationship.source_entity_id, relationship.target_entity_id})
            next_frontier -= visited
            remaining = max(arguments.max_nodes - len(visited), 0)
            frontier = set(sorted(next_frontier, key=str)[:remaining])
            visited.update(frontier)
        output = []
        for relationship in found.values():
            payload = {
                "relationship_id": str(relationship.id),
                "source_entity_id": str(relationship.source_entity_id),
                "target_entity_id": str(relationship.target_entity_id),
                "relationship_type": relationship.relationship_type,
                "valid_from": (
                    relationship.valid_from.isoformat() if relationship.valid_from else None
                ),
                "valid_to": relationship.valid_to.isoformat() if relationship.valid_to else None,
                "attributes": relationship.attributes,
            }
            evidence = await self._evidence(
                step=step,
                kind="relationship",
                source_kind="relationship",
                source_id=str(relationship.id),
                provenance_group=f"relationship:{relationship.relationship_type}",
                payload=payload,
                related_entity_ids=[
                    relationship.source_entity_id,
                    relationship.target_entity_id,
                ],
                observed_at=datetime.combine(
                    relationship.valid_from, datetime.min.time(), tzinfo=UTC
                )
                if relationship.valid_from
                else None,
            )
            output.append({**payload, "evidence_id": str(evidence.id)})
        return {
            "relationships": output,
            "nodes": [str(value) for value in sorted(visited, key=str)],
            "evidence_ids": [row["evidence_id"] for row in output],
        }
