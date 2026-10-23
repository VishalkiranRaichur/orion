import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_sources import find_workspace_data_source
from app.db import get_db
from app.models import DataSource, Workspace
from app.schemas.data_source import DataSourceCreate, DataSourceResponse
from app.workspaces import get_active_workspace, get_mutable_workspace

router = APIRouter()


@router.get("", response_model=list[DataSourceResponse])
async def list_data_sources(
    workspace: Workspace = Depends(get_active_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[DataSource]:
    return list(
        (
            await db.execute(
                select(DataSource)
                .where(DataSource.workspace_id == workspace.id)
                .order_by(DataSource.created_at, DataSource.id)
            )
        )
        .scalars()
        .all()
    )


@router.post("", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_data_source(
    request: DataSourceCreate,
    workspace: Workspace = Depends(get_mutable_workspace),
    db: AsyncSession = Depends(get_db),
) -> DataSource:
    data_source = DataSource(
        workspace_id=workspace.id,
        name=request.name,
        source_type=request.source_type,
        status="ready",
    )
    db.add(data_source)
    await db.commit()
    await db.refresh(data_source)
    return data_source


@router.get("/{data_source_id}", response_model=DataSourceResponse)
async def get_data_source(
    data_source_id: uuid.UUID,
    workspace: Workspace = Depends(get_active_workspace),
    db: AsyncSession = Depends(get_db),
) -> DataSource:
    data_source = await find_workspace_data_source(db, workspace.id, data_source_id)
    if data_source is None:
        raise HTTPException(status_code=404, detail="Data source not found.")
    return data_source
