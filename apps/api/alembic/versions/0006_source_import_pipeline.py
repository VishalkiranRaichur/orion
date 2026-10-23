"""Add source-item provenance and idempotent import identity."""

import sqlalchemy as sa

from alembic import op

revision = "0006_source_import_pipeline"
down_revision = "0005_data_source_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_data_sources_source_type",
        "data_sources",
        type_="check",
    )
    op.create_check_constraint(
        "ck_data_sources_source_type",
        "data_sources",
        "source_type IN ('upload', 'demo', 'local_fixture')",
    )

    op.add_column("documents", sa.Column("source_item_id", sa.String(500), nullable=True))
    op.add_column(
        "documents",
        sa.Column("source_modified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("source_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("documents", sa.Column("content_sha256", sa.String(64), nullable=True))
    op.create_check_constraint(
        "ck_documents_source_provenance_requires_source",
        "documents",
        "data_source_id IS NOT NULL OR "
        "(source_item_id IS NULL AND source_modified_at IS NULL AND source_synced_at IS NULL)",
    )
    op.create_check_constraint(
        "ck_documents_content_sha256_length",
        "documents",
        "content_sha256 IS NULL OR char_length(content_sha256) = 64",
    )
    op.create_index(
        "uq_documents_workspace_source_item",
        "documents",
        ["workspace_id", "data_source_id", "source_item_id"],
        unique=True,
        postgresql_where=sa.text("source_item_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_documents_workspace_source_item", table_name="documents")
    op.drop_constraint(
        "ck_documents_content_sha256_length",
        "documents",
        type_="check",
    )
    op.drop_constraint(
        "ck_documents_source_provenance_requires_source",
        "documents",
        type_="check",
    )
    op.drop_column("documents", "content_sha256")
    op.drop_column("documents", "source_synced_at")
    op.drop_column("documents", "source_modified_at")
    op.drop_column("documents", "source_item_id")

    op.drop_constraint(
        "ck_data_sources_source_type",
        "data_sources",
        type_="check",
    )
    op.create_check_constraint(
        "ck_data_sources_source_type",
        "data_sources",
        "source_type IN ('upload', 'demo')",
    )
