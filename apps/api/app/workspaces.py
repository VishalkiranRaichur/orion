from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, get_current_principal
from app.db import get_db
from app.models import Workspace


async def get_active_workspace(
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-ID"),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Workspace:
    if x_workspace_id is None:
        raise HTTPException(status_code=400, detail="X-Workspace-ID is required.")
    try:
        workspace_id = uuid.UUID(x_workspace_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="X-Workspace-ID must be a UUID.") from error
    workspace = (
        await db.execute(
            select(Workspace).where(
                Workspace.id == workspace_id,
                or_(Workspace.is_demo.is_(True), Workspace.owner_subject == principal.subject),
            )
        )
    ).scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return workspace


async def get_mutable_workspace(
    workspace: Workspace = Depends(get_active_workspace),
) -> Workspace:
    if workspace.is_demo:
        raise HTTPException(status_code=403, detail="The demo workspace is read-only.")
    return workspace
