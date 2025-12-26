from pydantic import BaseModel
from typing import Optional
from datetime import date
class DiagnosisInformation(BaseModel):
    primary_diagnosis : Optional[str] = None
    secondary_diagnosis : Optional[str] = None
    onset_date : Optional[date] = None
    classification : Optional[str] = None


class Allergies(BaseModel):
    known_allergies : Optional[str] = None


class PatientMedicalSchema(BaseModel):
    diagonisis_information : Optional[DiagnosisInformation]  = None
    allergies :  Optional[Allergies]  = None