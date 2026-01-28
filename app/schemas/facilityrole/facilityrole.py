from pydantic import BaseModel, EmailStr
from enum import Enum
from typing import Optional

class FacilityRoleEnum(str, Enum):
    ADMINISTRATION = "administration"
    DON = "director_of_nursing"
    MANAGER = "manager"

class FacilityRoleCreateSchema(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    role: FacilityRoleEnum
