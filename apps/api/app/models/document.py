import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "data_source_id"],
            ["data_sources.workspace_id", "data_sources.id"],
            name="fk_documents_workspace_data_source",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "data_source_id IS NOT NULL OR "
            "(source_item_id IS NULL AND source_modified_at IS NULL AND source_synced_at IS NULL)",
            name="ck_documents_source_provenance_requires_source",
        ),
        CheckConstraint(
            "content_sha256 IS NULL OR char_length(content_sha256) = 64",
            name="ck_documents_content_sha256_length",
        ),
        Index("ix_documents_workspace_created_at", "workspace_id", "created_at"),
        Index(
            "ix_documents_workspace_data_source_created_at",
            "workspace_id",
            "data_source_id",
            "created_at",
        ),
        Index(
            "uq_documents_workspace_source_item",
            "workspace_id",
            "data_source_id",
            "source_item_id",
            unique=True,
            postgresql_where=text("source_item_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )

    data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    source_item_id: Mapped[str | None] = mapped_column(String(500), nullable=True)

    source_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    source_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    storage_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="uploaded",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )
