from pydantic import BaseModel, Field
from typing import Optional

class SchedulerBase(BaseModel):
    email: str = Field(..., example="john.doe@example.com")
    first_name: str = Field(..., example="John")
    middle_name: Optional[str] = Field(None, example="A.")
    last_name: str = Field(..., example="Doe")
    phone: Optional[str] = Field(None, example="+1234567890")

class SchedulerResponse(BaseModel):
    success: bool
    message: str
    data: dict


class SchedulerCreate(SchedulerBase):
    
    password: str = Field(..., example="strongpassword123")
    


class PaginatedProductOut(BaseModel):
    total: int
    page: int
    limit: int
    items: list[SchedulerBase]


