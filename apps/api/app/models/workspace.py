import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

DEMO_WORKSPACE_ID = uuid.UUID("ad7b66e9-d22d-586e-84a2-2f39b030a356")
LEGACY_WORKSPACE_ID = uuid.UUID("da510dea-39ab-5ec6-bba6-4ccaa389cefc")


def utc_now() -> datetime:
    return datetime.now(UTC)


class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint(
            "owner_subject IS NOT NULL OR is_demo",
            name="ck_workspaces_demo_or_owned",
        ),
        Index("ix_workspaces_owner_subject", "owner_subject"),
        Index(
            "uq_workspaces_single_demo",
            "is_demo",
            unique=True,
            postgresql_where=text("is_demo"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    owner_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
