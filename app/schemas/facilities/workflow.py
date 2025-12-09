from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum   


class ADTWorkflow(BaseModel):
    adt_policy: Optional[str] = None       # Long text
    transfer_policy: Optional[str] = None  # Long text


class DocumentationWorkflow(BaseModel):
    discharge_summary_deadline_hours: Optional[int] = None
    provider_note_deadline_hours: Optional[str] = None



class ChargeCaptureEnum(str, Enum):
    Professional_Fee = "Perofessional Fee Only"
    Facility_Fee = "Facility Fee Only"
    both = "Both Professional and Facility"
    

class BillingWorkflow(BaseModel):
    billing_cutoff: Optional[str] = None
    charge_capture_method: Optional[ChargeCaptureEnum] = None  # e.g. "Daily", "Every Shift"


class ClinicalProtocols(BaseModel):
    stat_order_protocols: Optional[str] = None
    escalation_path: Optional[str] = None      # Example: "1. Nurse > 2. MD > 3. Admin"





class TransportVendor(BaseModel):
    vendor_name: Optional[str] = None
    contact_number: Optional[str] = None
   


class VaccineRules(BaseModel):
    visitation_policy: Optional[str] = None


class FacilityWorkflowSchema(BaseModel):
    adt_workflow: Optional[ADTWorkflow] = None
    documentation_workflow: Optional[DocumentationWorkflow] = None
    billing_workflow: Optional[BillingWorkflow] = None
    clinical_protocols: Optional[ClinicalProtocols] = None
    transport_vendors: List[TransportVendor] = Field(default_factory=list)
    vaccine_rules: Optional[VaccineRules] = None

