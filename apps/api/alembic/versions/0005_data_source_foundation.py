"""Add workspace-scoped data sources and document import origins."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_data_source_foundation"
down_revision = "0004_workspace_isolation"
branch_labels = None
depends_on = None

DEMO_WORKSPACE_ID = "ad7b66e9-d22d-586e-84a2-2f39b030a356"
DEMO_DATA_SOURCE_ID = "f42e7ff6-554b-5085-829f-ae80983bcc38"


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("external_key", sa.String(255), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('upload', 'demo')",
            name="ck_data_sources_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'error')",
            name="ck_data_sources_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_data_sources_workspace_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_data_sources_workspace_id_id",
        ),
    )
    op.create_index(
        "uq_data_sources_workspace_type_external_key",
        "data_sources",
        ["workspace_id", "source_type", "external_key"],
        unique=True,
        postgresql_where=sa.text("external_key IS NOT NULL"),
    )
    op.create_index(
        "ix_data_sources_workspace_created_at",
        "data_sources",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "ix_data_sources_workspace_status",
        "data_sources",
        ["workspace_id", "status"],
    )

    op.add_column(
        "documents",
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.execute(
        sa.text(
            """INSERT INTO data_sources
               (id, workspace_id, name, source_type, status, external_key,
                last_synced_at, error, created_at, updated_at)
               VALUES (
                 CAST(:source_id AS uuid), CAST(:workspace_id AS uuid),
                 'ORION Demo Import', 'demo', 'ready', 'demo:orion_company',
                 (SELECT max(created_at) FROM documents
                  WHERE workspace_id = CAST(:workspace_id AS uuid)),
                 NULL, now(), now()
               )"""
        ).bindparams(source_id=DEMO_DATA_SOURCE_ID, workspace_id=DEMO_WORKSPACE_ID)
    )
    op.execute(
        sa.text(
            """UPDATE documents
               SET data_source_id = CAST(:source_id AS uuid)
               WHERE workspace_id = CAST(:workspace_id AS uuid)"""
        ).bindparams(source_id=DEMO_DATA_SOURCE_ID, workspace_id=DEMO_WORKSPACE_ID)
    )
    op.execute(
        """DO $$ BEGIN
           IF EXISTS (
             SELECT 1 FROM documents d
             JOIN data_sources source ON source.id = d.data_source_id
             WHERE d.data_source_id IS NOT NULL
               AND d.workspace_id <> source.workspace_id
           ) THEN
             RAISE EXCEPTION
               'Data source migration found a document associated with another workspace';
           END IF;
           END $$"""
    )

    op.create_foreign_key(
        "fk_documents_workspace_data_source",
        "documents",
        "data_sources",
        ["workspace_id", "data_source_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_documents_workspace_data_source_created_at",
        "documents",
        ["workspace_id", "data_source_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_documents_workspace_data_source_created_at",
        table_name="documents",
    )
    op.drop_constraint(
        "fk_documents_workspace_data_source",
        "documents",
        type_="foreignkey",
    )
    op.drop_column("documents", "data_source_id")
    op.drop_index("ix_data_sources_workspace_status", table_name="data_sources")
    op.drop_index("ix_data_sources_workspace_created_at", table_name="data_sources")
    op.drop_index(
        "uq_data_sources_workspace_type_external_key",
        table_name="data_sources",
    )
    op.drop_table("data_sources")
