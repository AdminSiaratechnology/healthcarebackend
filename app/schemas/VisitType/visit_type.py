from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from beanie import PydanticObjectId


class VisitTypeCreate(BaseModel):
    name: str = Field(..., description="Name of the visit type")


class VisitTypeUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None


class VisitTypeResponse(BaseModel):
    id: PydanticObjectId
    name: str
    status: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaginatedVisitTypeResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: list[VisitTypeResponse]

