from pydantic import BaseModel
from typing import Optional
from enum import Enum
from datetime import date

class AccreditationsBodyEnum(str, Enum):
    joint_comission = "The Joint Commission"
    carf_international = "CARF International"
    dnv_healthcare = "DNV Healthcare"
    other = "Other"

class AccreditationStatusEnum(str, Enum):
    Active = "Active"
    Pending = "Pending"
    Expired = "Expired"
    under_review = "Under Review"


class AccreditationsSchema(BaseModel):
    accreditations_body: Optional[AccreditationsBodyEnum] = None
    accreditation_status : Optional[AccreditationStatusEnum] =  AccreditationStatusEnum.Active
    expiry_date : date
    certificate_file_id : Optional[str] = None
