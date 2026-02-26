from pydantic import BaseModel
from typing import Optional
from enum import Enum
from beanie import PydanticObjectId, Link
from app.patients.models.patients import PatientDoc

class DegreeEnum(str, Enum):
    MD = "MD- Doctor of Medicine"
    DO = "DO-Doctor of Osteopathic Medicine"
    NP = "Nurse Practitioner"
    PA = "Physicain Assistant"

class Speciality(str, Enum):
    InternalMedicine = "Internal Medicine"
    family_medicine = "Family Medicine"
    cardiology = "Cardiology"
    geriatric_medicine = "Geriatric Medicine"
    emergency_medicine = "Emergency Medicine"

class BasicInfo(BaseModel):
    profile_pic: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    degree_enum: Optional[DegreeEnum] = None
    speciality: Optional[Speciality] = None
    subspeciality: Optional[str] = None
    npi_no: Optional[str] = None
    taxonomy_code: Optional[str] = None
    license_no: Optional[str] = None
    license_state: Optional[str] = None
    dea_no: Optional[str] = None
    dea_expiration_date: Optional[str] = None
    professional_email: Optional[str] = None
    professional_phone: Optional[str] = None
    



class PatientIdProjection(BaseModel):
    patient_id: Link["PatientDoc"]

    model_config = {
        "arbitrary_types_allowed": True
    }