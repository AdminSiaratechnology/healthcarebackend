from pydantic import BaseModel
from typing import Optional
from enum import Enum








class shiftDepartmentEnum(str, Enum):
    Hospitalist = "Hospitalist"
    SNF_Team = "SNF Team"
    Phychiatry = "Psychiatry"
    Emergency = "Emergency"


class ShiftTypeEnum(str, Enum):
    Day = "Day"
    Night = "Night"
    Evening = "Evening"


class PriotityEnum(str, Enum):
    High = "High"
    Medium = "Medium"
    Low = "Low"


class RequiredRoleEnum(str, Enum):
    MD = "MD-Medical Doctor"
    NP = "Nurse Practitioner"
    PA = "physician Assistant"
    RN = "Registered Nurse"


class DaysOfWeekEnum(str, Enum):
    Monday = "Monday"
    Tuesday = "Tuesday"
    Wednesday = "Wednesday"
    Thursday = "Thursday"
    Friday = "Friday"
    Saturday = "Saturday"
    Sunday = "Sunday"

class ShiftManagementSchema(BaseModel):
    name : str
    shift : Optional[shiftDepartmentEnum] = None
    start_time : Optional[str] = None
    end_time : Optional[str] = None
    shift_type : Optional[ShiftTypeEnum] = None
    break_duration : Optional[str] = None
    minumum_staff_required : Optional[int] = None
    maximum_staff_allowed : Optional[int] = None
    priority : Optional[PriotityEnum] = None
    required_role : Optional[list[RequiredRoleEnum]] = None
    active_days : Optional[list[DaysOfWeekEnum]] = None
    description : Optional[str] = None
    facility_ids : Optional[list[str]] = None
    