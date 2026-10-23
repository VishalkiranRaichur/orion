import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, get_current_principal
from app.db import get_db
from app.models import Workspace
from app.schemas.workspace import WorkspaceCreate, WorkspaceResponse

router = APIRouter()


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[Workspace]:
    return list(
        (
            await db.execute(
                select(Workspace)
                .where(
                    or_(Workspace.is_demo.is_(True), Workspace.owner_subject == principal.subject)
                )
                .order_by(Workspace.is_demo, Workspace.created_at, Workspace.id)
            )
        )
        .scalars()
        .all()
    )


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    request: WorkspaceCreate,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Workspace:
    workspace = Workspace(
        name=request.name,
        industry=request.industry,
        owner_subject=principal.subject,
        is_demo=False,
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)
    return workspace


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Workspace:
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
