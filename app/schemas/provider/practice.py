from pydantic import BaseModel
from typing import Optional
from enum import Enum

class AssignedPractice(str, Enum):
    Serion_health = "Serion Health"
    Caremed_partners = "CareMed Partners"
    wellness_group = "Wellness Group"


class VisitType(str, Enum):
    Wound_care_visit = "Wound Care Visit"
    acute_visit = "Acute Visit"
    medicare_compliance_visit = "Medicare Compliance Visit"
    follow_up_visit = "Follow-up Visit"
    routine_check = "Routine Check"


class BillingLocationCode(str, Enum):
    pos_31_skilled_nursing_facility = "POS 31 - Skilled Nursing Facility"    
    pos32_nursing_facility = "POS 32 - Nursing Facility"
    pos_61_comprehensive_inpatient_rehab ="POS 61 - Comprehensive Inpatient Rehab"
    pos_13_assisted_living_facility = "POS 13 - Assisted Living Facility"

    
class RotationDays(BaseModel):
    monday: bool = False
    tuesday: bool = False
    wednesday: bool = False
    thursday: bool = False
    friday: bool = False

    

class OncallDays(BaseModel):
    sunday : bool = False
    monday: bool = False
    tuesday: bool = False
    wednesday: bool = False
    thursday: bool = False
    friday: bool = False
    saturday : bool = False



class PracticeSchema(BaseModel):
    assigned_practice : Optional[AssignedPractice] = None
    rotation_days : Optional[RotationDays] = None
    on_call_days : Optional[OncallDays] = None
    visit_type : Optional[VisitType] = None
    billing_location_code : Optional[BillingLocationCode] = None
    provider_id: Optional[str] = None
    facility_ids: Optional[list[str]] = None
    primary_facility_id: Optional[str] = None


