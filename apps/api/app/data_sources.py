import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DataSource


async def find_workspace_data_source(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    data_source_id: uuid.UUID,
) -> DataSource | None:
    return (
        await db.execute(
            select(DataSource).where(
                DataSource.id == data_source_id,
                DataSource.workspace_id == workspace_id,
            )
        )
    ).scalar_one_or_none()
