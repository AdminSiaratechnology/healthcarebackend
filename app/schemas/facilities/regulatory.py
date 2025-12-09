from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
from enum import Enum


# ✅ State License
class StateLicense(BaseModel):
    state_license_number: str
    license_state: str
    license_expiry_date: date


# ✅ Federal Certification
class FederalCertification(BaseModel):
    medicare_certified: bool
    medicaid_certified: bool


# ✅ Accreditation Enums
class AccreditationBodyEnum(str, Enum):
    THE_JOINT_COMMISSION = "The Joint Commission"
    CARF = "CARF International"
    DNV_HC = "DNV Healthcare"
    OTHER = "OTHER"


class AccreditationStatusEnum(str, Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    PENDING = "Pending"
    EXPIRED = "Expired"
    UNDER_REVIEW = "Under Review"


# ✅ Accreditation Model
class Accreditation(BaseModel):
    accreditation_body: Optional[AccreditationBodyEnum]
    accreditation_status: Optional[AccreditationStatusEnum]
    expiry_date: Optional[date]
    certificate_file_id: Optional[str]


# ✅ ONC Certification
class ONCCertification(BaseModel):
    onc_certification_notes: Optional[str]
    attestation_year: int


# ✅ State Reporting Identifier
class StateReportingIdentifier(BaseModel):
    registry_system_name: str
    identifier_value: str


# ✅ MAIN REGULATORY MODEL (Facility Linked)
class RegulatorySchema(BaseModel):
    state_license: Optional[StateLicense]
    federal_certification: Optional[FederalCertification]
    accreditations: List[Accreditation] = Field(default_factory=list)
    onc_certification: Optional[ONCCertification]
    state_reporting_identifier: List[StateReportingIdentifier] = Field(default_factory=list)
