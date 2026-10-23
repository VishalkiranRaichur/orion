from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_sources import find_workspace_data_source
from app.models import DataSource, Workspace
from app.services.source_import import NormalizedIngestionItem

LOCAL_FIXTURE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "orion:local-fixture-source")


class FixtureManifestItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_item_id: str = Field(min_length=1, max_length=500)
    filename: str = Field(min_length=1, max_length=255)
    path: str = Field(min_length=1)
    content_type: str = Field(min_length=1, max_length=100)
    source_modified_at: datetime | None = None


class FixtureManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_key: str = Field(min_length=1, max_length=200)
    items: list[FixtureManifestItem]


class LocalFixtureImporter:
    source_type = "local_fixture"

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        manifest_path = self.root / "manifest.json"
        self.manifest = FixtureManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )

    async def load_items(self) -> list[NormalizedIngestionItem]:
        items: list[NormalizedIngestionItem] = []
        for manifest_item in self.manifest.items:
            path = (self.root / manifest_item.path).resolve()
            try:
                path.relative_to(self.root)
            except ValueError as error:
                raise ValueError(
                    "Fixture item path must remain inside its fixture root."
                ) from error
            if not path.is_file():
                raise ValueError(f"Fixture item does not exist: {manifest_item.path}")
            items.append(
                NormalizedIngestionItem(
                    source_item_id=manifest_item.source_item_id,
                    filename=manifest_item.filename,
                    content_type=manifest_item.content_type,
                    content=path.read_bytes(),
                    source_modified_at=manifest_item.source_modified_at,
                )
            )
        return items


def local_fixture_source_id(workspace_id: uuid.UUID, fixture_key: str) -> uuid.UUID:
    return uuid.uuid5(LOCAL_FIXTURE_NAMESPACE, f"{workspace_id}:{fixture_key}")


async def ensure_local_fixture_source(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    owner_subject: str,
    fixture_key: str,
    name: str,
) -> DataSource:
    workspace = (
        await db.execute(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.owner_subject == owner_subject,
                Workspace.is_demo.is_(False),
            )
        )
    ).scalar_one_or_none()
    if workspace is None:
        raise ValueError("Private workspace is not available to the local operator.")

    source_id = local_fixture_source_id(workspace_id, fixture_key)
    source = await find_workspace_data_source(db, workspace_id, source_id)
    if source is None:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Local fixture source name cannot be empty.")
        if len(cleaned_name) > 120:
            raise ValueError("Local fixture source name cannot exceed 120 characters.")
        source = DataSource(
            id=source_id,
            workspace_id=workspace_id,
            name=cleaned_name,
            source_type="local_fixture",
            status="ready",
            external_key=f"local_fixture:{fixture_key}",
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)
    elif source.source_type != "local_fixture":
        raise ValueError("Deterministic local fixture source ID is already in use.")
    return source
