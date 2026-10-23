import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    data_source_id: uuid.UUID | None
    source_item_id: str | None
    source_modified_at: datetime | None
    source_synced_at: datetime | None
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str
    status: str
    created_at: datetime
