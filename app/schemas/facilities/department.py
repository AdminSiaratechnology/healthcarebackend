from pydantic import BaseModel
from typing import Optional
from enum import Enum

class TypeOfDepartment(str, Enum):
    Nursing = "Nursing"
    MemoryCare = "MemoryCare"
    Rehab = "Rehab"
    Hospice = "Hospice"
    BehavioralHealth = "BehavioralHealth"
    Admin = "Admin"
    Other = "Other"


class DepartmentSchema(BaseModel):
    code :  Optional[str] = None
    name : Optional[str] = None
    type: Optional[TypeOfDepartment] = None
    description: Optional[str] = None