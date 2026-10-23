import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

DEMO_DATA_SOURCE_ID = uuid.UUID("f42e7ff6-554b-5085-829f-ae80983bcc38")


def utc_now() -> datetime:
    return datetime.now(UTC)


class DataSource(Base):
    __tablename__ = "data_sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('upload', 'demo', 'local_fixture')",
            name="ck_data_sources_source_type",
        ),
        CheckConstraint(
            "status IN ('ready', 'error')",
            name="ck_data_sources_status",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_data_sources_workspace_id_id",
        ),
        Index(
            "uq_data_sources_workspace_type_external_key",
            "workspace_id",
            "source_type",
            "external_key",
            unique=True,
            postgresql_where=text("external_key IS NOT NULL"),
        ),
        Index("ix_data_sources_workspace_created_at", "workspace_id", "created_at"),
        Index("ix_data_sources_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ready")
    external_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
