from pydantic import BaseModel, EmailStr
from enum import Enum
from typing import Optional


class FacilityRoleEnum(str, Enum):
    ADMINISTRATION = "administration"
    DON = "director_of_nursing"
    MANAGER = "manager"
    MEDICAL_DIRECTOR = "medical_director"
    ADMISSIONS_COORDINATOR = "admissions_coordinator"
    IT_ADMINISTRATOR = "it_administrator"
    CHARGE_NURSE = "charge_nurse"


class FacilityRoleCreateSchema(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    role: FacilityRoleEnum
