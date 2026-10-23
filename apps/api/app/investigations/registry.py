from dataclasses import dataclass

from app.schemas.investigation import BusinessRecordType, EntityType, InvestigationToolKind


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    aliases: frozenset[str]
    unit: str


METRICS = {
    "recognized_revenue_usd": MetricDefinition(
        key="recognized_revenue_usd",
        aliases=frozenset({"revenue", "recognized revenue", "monthly revenue"}),
        unit="USD",
    )
}

ENABLED_TOOLS = frozenset(InvestigationToolKind)
ENTITY_TYPES = frozenset(EntityType)
RECORD_TYPES = frozenset(BusinessRecordType)


def resolve_metric(value: str) -> str:
    normalized = value.strip().lower().replace("_", " ")
    for definition in METRICS.values():
        if value == definition.key or normalized in definition.aliases:
            return definition.key
    from app.investigations.errors import UnsupportedMetricError

    raise UnsupportedMetricError(f"Unsupported metric: {value}")
