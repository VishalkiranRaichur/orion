import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    industry: str | None = Field(default=None, max_length=120)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Workspace name cannot be empty")
        return value

    @field_validator("industry")
    @classmethod
    def clean_industry(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    industry: str | None
    is_demo: bool
    created_at: datetime
    updated_at: datetime
