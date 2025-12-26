from pydantic import BaseModel
from typing import Optional
from enum import Enum
from datetime import date

class AccreditationsBodyEnum(str, Enum):
    joint_comission = "The Joint Commission"
    carf_international = "CARF International"
    dnv_healthcare = "DNV Healthcare"
    other = "Other"

class StatusEnum(str, Enum):
    Active = "Active"
    Pending = "Pending"
    Expired = "Expired"
    under_review = "Under Review"


class AccreditationsSchema(BaseModel):
    accreditations: Optional[AccreditationsBodyEnum] = None
    status : Optional[StatusEnum] =  StatusEnum.Active
    expiry_date : date
    certificate_file_id : Optional[str] = None
