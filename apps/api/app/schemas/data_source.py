import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DataSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source_type: Literal["upload"] = "upload"

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Data source name cannot be empty")
        return value


class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    source_type: str
    status: str
    external_key: str | None
    last_synced_at: datetime | None
    error: str | None
    created_at: datetime
    updated_at: datetime
