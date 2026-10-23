"""Add company workspaces and isolate all persisted capabilities."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_workspace_isolation"
down_revision = "0003_investigation_engine"
branch_labels = None
depends_on = None

DEMO_ID = "ad7b66e9-d22d-586e-84a2-2f39b030a356"
LEGACY_ID = "da510dea-39ab-5ec6-bba6-4ccaa389cefc"

SCOPED_TABLES = (
    "documents",
    "document_chunks",
    "investigations",
    "investigation_steps",
    "entities",
    "relationships",
    "metric_observations",
    "business_records",
    "evidence_items",
    "claims",
)


def _fail_if(query: str, message: str) -> None:
    op.execute(
        sa.text(
            f"""DO $$ BEGIN
            IF EXISTS ({query}) THEN
                RAISE EXCEPTION '{message}';
            END IF;
            END $$"""
        )
    )


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("industry", sa.String(120), nullable=True),
        sa.Column("owner_subject", sa.String(255), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "owner_subject IS NOT NULL OR is_demo", name="ck_workspaces_demo_or_owned"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspaces_owner_subject", "workspaces", ["owner_subject"])
    op.create_index(
        "uq_workspaces_single_demo",
        "workspaces",
        ["is_demo"],
        unique=True,
        postgresql_where=sa.text("is_demo"),
    )
    op.execute(
        sa.text(
            """INSERT INTO workspaces
               (id, name, industry, owner_subject, is_demo, created_at, updated_at)
               VALUES (CAST(:id AS uuid), 'ORION Demo Company', 'Software', NULL, true,
                       now(), now())"""
        ).bindparams(id=DEMO_ID)
    )

    for table in SCOPED_TABLES:
        op.add_column(
            table,
            sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    op.add_column("investigations", sa.Column("created_by_subject", sa.String(255), nullable=True))

    # A legacy owner is created only if the pre-Phase-4 database contains persisted rows.
    legacy_exists = " OR ".join(f"EXISTS (SELECT 1 FROM {table})" for table in SCOPED_TABLES)
    op.execute(
        sa.text(
            f"""INSERT INTO workspaces
                (id, name, industry, owner_subject, is_demo, created_at, updated_at)
                SELECT CAST(:id AS uuid), 'Legacy Workspace', NULL, 'local-dev', false,
                       now(), now()
                WHERE {legacy_exists}
                ON CONFLICT (id) DO NOTHING"""
        ).bindparams(id=LEGACY_ID)
    )

    # Classify roots by deterministic demo signals, then inherit scope through parents.
    op.execute(
        sa.text(
            """UPDATE documents SET workspace_id = CASE
                 WHEN storage_key LIKE 'demo/orion_company/%' THEN CAST(:demo AS uuid)
                 ELSE CAST(:legacy AS uuid) END"""
        ).bindparams(demo=DEMO_ID, legacy=LEGACY_ID)
    )
    op.execute(
        sa.text(
            """UPDATE entities SET workspace_id = CASE
                 WHEN external_key LIKE 'demo:%' OR attributes @> '{"demo": true}'::jsonb
                 THEN CAST(:demo AS uuid) ELSE CAST(:legacy AS uuid) END"""
        ).bindparams(demo=DEMO_ID, legacy=LEGACY_ID)
    )
    op.execute(
        """UPDATE document_chunks c SET workspace_id = d.workspace_id
           FROM documents d WHERE d.id = c.document_id"""
    )

    _fail_if(
        """SELECT 1 FROM relationships r
           JOIN entities source ON source.id = r.source_entity_id
           JOIN entities target ON target.id = r.target_entity_id
           WHERE source.workspace_id <> target.workspace_id""",
        "Workspace migration found a relationship with cross-workspace endpoints",
    )
    op.execute(
        """UPDATE relationships r SET workspace_id = source.workspace_id
           FROM entities source, entities target
           WHERE source.id = r.source_entity_id AND target.id = r.target_entity_id
             AND source.workspace_id = target.workspace_id"""
    )
    op.execute(
        sa.text(
            """UPDATE business_records b SET workspace_id = CASE
                 WHEN b.external_key LIKE 'demo:%'
                   OR b.attributes @> '{"demo": true}'::jsonb
                   OR EXISTS (SELECT 1 FROM entities e WHERE e.id = b.primary_entity_id
                              AND e.workspace_id = CAST(:demo AS uuid))
                 THEN CAST(:demo AS uuid) ELSE CAST(:legacy AS uuid) END"""
        ).bindparams(demo=DEMO_ID, legacy=LEGACY_ID)
    )
    op.execute(
        sa.text(
            """UPDATE metric_observations m SET workspace_id = CASE
                 WHEN m.dimensions @> '{"demo": true}'::jsonb
                   OR EXISTS (SELECT 1 FROM entities e WHERE e.id = m.entity_id
                              AND e.workspace_id = CAST(:demo AS uuid))
                 THEN CAST(:demo AS uuid) ELSE CAST(:legacy AS uuid) END"""
        ).bindparams(demo=DEMO_ID, legacy=LEGACY_ID)
    )

    # Only evidence-backed, unambiguously demo investigations move to the shared demo scope.
    op.execute(
        sa.text(
            """UPDATE investigations i SET workspace_id = CASE WHEN
                 EXISTS (SELECT 1 FROM evidence_items ev
                         WHERE ev.investigation_id = i.id AND ev.evidence_kind <> 'calculation')
                 AND NOT EXISTS (
                   SELECT 1 FROM evidence_items ev
                   WHERE ev.investigation_id = i.id AND ev.evidence_kind <> 'calculation'
                     AND ((ev.source_kind = 'metric_observation' AND EXISTS (
                            SELECT 1 FROM metric_observations m
                            WHERE m.id::text = ev.source_id
                              AND m.workspace_id <> CAST(:demo AS uuid)))
                       OR (ev.source_kind IN ('crm_activity','support_incident','project_update',
                                             'renewal_event','business_record') AND EXISTS (
                            SELECT 1 FROM business_records b
                            WHERE b.id::text = ev.source_id
                              AND b.workspace_id <> CAST(:demo AS uuid)))
                       OR (ev.evidence_kind = 'document_chunk' AND EXISTS (
                            SELECT 1 FROM document_chunks c
                            WHERE c.id::text = ev.source_id
                              AND c.workspace_id <> CAST(:demo AS uuid)))
                       OR (ev.evidence_kind = 'relationship' AND EXISTS (
                            SELECT 1 FROM relationships r
                            WHERE r.id::text = ev.source_id
                              AND r.workspace_id <> CAST(:demo AS uuid))))
                 )
                 AND EXISTS (
                   SELECT 1 FROM evidence_items ev
                   WHERE ev.investigation_id = i.id
                     AND ((ev.source_kind = 'metric_observation' AND EXISTS (
                            SELECT 1 FROM metric_observations m
                            WHERE m.id::text = ev.source_id
                              AND m.workspace_id = CAST(:demo AS uuid)))
                       OR (ev.source_kind IN ('crm_activity','support_incident','project_update',
                                             'renewal_event','business_record') AND EXISTS (
                            SELECT 1 FROM business_records b
                            WHERE b.id::text = ev.source_id
                              AND b.workspace_id = CAST(:demo AS uuid)))
                       OR (ev.evidence_kind = 'document_chunk' AND EXISTS (
                            SELECT 1 FROM document_chunks c
                            WHERE c.id::text = ev.source_id
                              AND c.workspace_id = CAST(:demo AS uuid)))
                       OR (ev.evidence_kind = 'relationship' AND EXISTS (
                            SELECT 1 FROM relationships r
                            WHERE r.id::text = ev.source_id
                              AND r.workspace_id = CAST(:demo AS uuid))))
                 ) THEN CAST(:demo AS uuid) ELSE CAST(:legacy AS uuid) END,
                 created_by_subject = 'local-dev'"""
        ).bindparams(demo=DEMO_ID, legacy=LEGACY_ID)
    )
    for table in ("investigation_steps", "evidence_items", "claims"):
        op.execute(
            f"""UPDATE {table} child SET workspace_id = i.workspace_id
                FROM investigations i WHERE i.id = child.investigation_id"""
        )

    # Reject contradictions rather than silently choosing a scope.
    _fail_if(
        """SELECT 1 FROM business_records b JOIN entities e ON e.id=b.primary_entity_id
           WHERE b.workspace_id <> e.workspace_id""",
        "Workspace migration found a business record with a cross-workspace primary entity",
    )
    _fail_if(
        """SELECT 1 FROM business_records b JOIN entities e ON e.id=b.related_entity_id
           WHERE b.workspace_id <> e.workspace_id""",
        "Workspace migration found a business record with a cross-workspace related entity",
    )
    _fail_if(
        """SELECT 1 FROM metric_observations m JOIN entities e ON e.id=m.entity_id
           WHERE m.workspace_id <> e.workspace_id""",
        "Workspace migration found a metric with a cross-workspace entity",
    )
    for table in ("relationships", "metric_observations", "business_records"):
        _fail_if(
            f"""SELECT 1 FROM {table} child JOIN documents d ON d.id=child.source_document_id
                WHERE child.workspace_id <> d.workspace_id""",
            f"Workspace migration found a {table} source document in another workspace",
        )
    _fail_if(
        """SELECT 1 FROM claim_evidence ce
           JOIN claims c ON c.id=ce.claim_id JOIN evidence_items e ON e.id=ce.evidence_id
           WHERE c.workspace_id <> e.workspace_id""",
        "Workspace migration found a cross-workspace claim/evidence link",
    )
    _fail_if(
        " UNION ALL ".join(
            f"SELECT 1 FROM {table} WHERE workspace_id IS NULL" for table in SCOPED_TABLES
        ),
        "Workspace migration left unscoped persisted rows",
    )

    for table in SCOPED_TABLES:
        op.alter_column(table, "workspace_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_workspace_id",
            table,
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="CASCADE",
        )
    op.alter_column("investigations", "created_by_subject", nullable=False)

    op.drop_constraint("uq_entity_type_external_key", "entities", type_="unique")
    op.create_unique_constraint(
        "uq_entity_workspace_type_key", "entities", ["workspace_id", "entity_type", "external_key"]
    )
    op.drop_constraint("uq_business_record_type_key", "business_records", type_="unique")
    op.create_unique_constraint(
        "uq_business_record_workspace_type_key",
        "business_records",
        ["workspace_id", "record_type", "external_key"],
    )

    indexes = {
        "documents": ("ix_documents_workspace_created_at", ["workspace_id", "created_at"]),
        "document_chunks": (
            "ix_document_chunks_workspace_document",
            ["workspace_id", "document_id"],
        ),
        "investigations": (
            "ix_investigations_workspace_created_at",
            ["workspace_id", "created_at"],
        ),
        "investigation_steps": (
            "ix_investigation_steps_workspace_investigation",
            ["workspace_id", "investigation_id"],
        ),
        "entities": ("ix_entities_workspace_type", ["workspace_id", "entity_type"]),
        "relationships": (
            "ix_relationships_workspace_source",
            ["workspace_id", "source_entity_id"],
        ),
        "metric_observations": (
            "ix_metric_observations_workspace_metric_period",
            ["workspace_id", "metric_key", "period_start"],
        ),
        "business_records": (
            "ix_business_records_workspace_type_occurred",
            ["workspace_id", "record_type", "occurred_at"],
        ),
        "evidence_items": (
            "ix_evidence_items_workspace_investigation",
            ["workspace_id", "investigation_id"],
        ),
        "claims": ("ix_claims_workspace_investigation", ["workspace_id", "investigation_id"]),
    }
    for table, (name, columns) in indexes.items():
        op.create_index(name, table, columns)
    op.create_index(
        "ix_relationships_workspace_target",
        "relationships",
        ["workspace_id", "target_entity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_relationships_workspace_target", table_name="relationships")
    names = {
        "documents": "ix_documents_workspace_created_at",
        "document_chunks": "ix_document_chunks_workspace_document",
        "investigations": "ix_investigations_workspace_created_at",
        "investigation_steps": "ix_investigation_steps_workspace_investigation",
        "entities": "ix_entities_workspace_type",
        "relationships": "ix_relationships_workspace_source",
        "metric_observations": "ix_metric_observations_workspace_metric_period",
        "business_records": "ix_business_records_workspace_type_occurred",
        "evidence_items": "ix_evidence_items_workspace_investigation",
        "claims": "ix_claims_workspace_investigation",
    }
    for table, name in names.items():
        op.drop_index(name, table_name=table)
    op.drop_constraint("uq_business_record_workspace_type_key", "business_records", type_="unique")
    op.create_unique_constraint(
        "uq_business_record_type_key", "business_records", ["record_type", "external_key"]
    )
    op.drop_constraint("uq_entity_workspace_type_key", "entities", type_="unique")
    op.create_unique_constraint(
        "uq_entity_type_external_key", "entities", ["entity_type", "external_key"]
    )
    op.drop_column("investigations", "created_by_subject")
    for table in reversed(SCOPED_TABLES):
        op.drop_constraint(f"fk_{table}_workspace_id", table, type_="foreignkey")
        op.drop_column(table, "workspace_id")
    op.drop_index("uq_workspaces_single_demo", table_name="workspaces")
    op.drop_index("ix_workspaces_owner_subject", table_name="workspaces")
    op.drop_table("workspaces")
