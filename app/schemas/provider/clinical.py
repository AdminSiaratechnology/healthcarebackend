from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class  DefaultnoteTemplate(str, Enum):
    Admission = "Admission H&P"
    
class MedicationSchema(BaseModel):
    name: str
    


class LabTestSchema(BaseModel):
    name: str
    



class OrderSchema(BaseModel):
    name: str
    


class WorkflowAutomationSchema(BaseModel):
    is_erx_enabled : bool = False
    is_signature_notes : bool = False
    is_require_supervising_signature : bool = False
    is_populate_diagnoses : bool = False


class ClinicalDataSchema(BaseModel):
    default_note_template: Optional[DefaultnoteTemplate] = None
    medications: Optional[List[MedicationSchema]] = None
    lab_tests: Optional[List[LabTestSchema]] = None
    orders: Optional[List[OrderSchema]] = None
    statement: Optional[str] = None
    work_flow_automation: Optional[WorkflowAutomationSchema] = None
