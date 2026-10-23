"""Add the ORION Phase 2 investigation engine data contract."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_investigation_engine"
down_revision = "0002_investigation_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigations", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("UPDATE investigations SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column("investigations", "updated_at", nullable=False)
    op.add_column(
        "investigations", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("investigations", sa.Column("failure_code", sa.String(64), nullable=True))
    op.add_column(
        "investigations",
        sa.Column(
            "execution_usage",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_table(
        "business_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_type", sa.String(64), nullable=False),
        sa.Column("external_key", sa.String(255), nullable=False),
        sa.Column("primary_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("related_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_locator", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["primary_entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["related_entity_id"], ["entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("record_type", "external_key", name="uq_business_record_type_key"),
    )
    op.create_index(
        "ix_business_records_type_occurred", "business_records", ["record_type", "occurred_at"]
    )
    op.create_index(
        "ix_business_records_primary_occurred",
        "business_records",
        ["primary_entity_id", "occurred_at"],
    )
    op.create_index(
        "ix_business_records_related_occurred",
        "business_records",
        ["related_entity_id", "occurred_at"],
    )

    op.add_column(
        "evidence_items",
        sa.Column("provenance_group", sa.String(255), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "evidence_items",
        sa.Column(
            "source_locator", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.add_column(
        "evidence_items",
        sa.Column(
            "related_entity_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("evidence_items", "related_entity_ids")
    op.drop_column("evidence_items", "source_locator")
    op.drop_column("evidence_items", "provenance_group")
    op.drop_index("ix_business_records_related_occurred", table_name="business_records")
    op.drop_index("ix_business_records_primary_occurred", table_name="business_records")
    op.drop_index("ix_business_records_type_occurred", table_name="business_records")
    op.drop_table("business_records")
    op.drop_column("investigations", "execution_usage")
    op.drop_column("investigations", "failure_code")
    op.drop_column("investigations", "attempt_count")
    op.drop_column("investigations", "updated_at")
