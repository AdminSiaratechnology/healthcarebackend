from pydantic import BaseModel
from typing import Optional

class EmergencyContact(BaseModel):
    name : Optional[str] = None
    relationship : Optional[str] = None
    phone_number : Optional[str] = None

class SecondaryEmergencyContact(BaseModel):
    name : Optional[str] = None
    relationship : Optional[str] = None
    phone_number : Optional[str] = None


class PatientEmergencyContact(BaseModel):
    emergency_contact : Optional[EmergencyContact]  = None
    secondary_contact : Optional[SecondaryEmergencyContact]  = None
