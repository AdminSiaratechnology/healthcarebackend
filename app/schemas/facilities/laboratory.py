from pydantic import BaseModel
from typing import Optional
from enum import Enum

class interfaceType(str, Enum):
    HL7 = "HL7"
    FHIR = "FHIR"
    PORTAL = "PORTAL"

class LoincPolicy(str, Enum):
    LabSupplied = "LabSupplied"
    InternalMap = "InternalMap"

class LaboratorySchema(BaseModel):
    laboratory_name: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    pickup_schedule: Optional[str] = None
    interface_type: Optional[interfaceType] = None
    loinc_policy: Optional[LoincPolicy] = None