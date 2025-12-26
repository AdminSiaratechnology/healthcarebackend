from pydantic import BaseModel,EmailStr
from typing import Optional
from datetime import date
from enum import Enum

class AdmissionTypeEnum(str, Enum):
    Elective = "Elective"
    Emergency = "Emergency"
    transfer = "Transfer"
    Other = "Other"

class PatientStatus(str, Enum):
    Active = "Active"
    Inactive = "Inactive"
    Discharged = "Discharged"
    Transferred = "Transferred"


class AdmittedForm(str, Enum):
    Home = "Home"
    Hospital = "Hospital"
    NursingHome = "Nursing Home"
    Other_facility = "Other Facility"

class PatientAdmissionSchema(BaseModel):
    admission_date : date
    room_id : str
    original_admission_date : Optional[date] = None
    bed_id : str
    admission_location : Optional[str] = None
    resident_number : Optional[str] = None
    admission_type : AdmissionTypeEnum
    status : PatientStatus = PatientStatus.Active   
    admitted_form : AdmittedForm
    from_date : date
    to_date : date

