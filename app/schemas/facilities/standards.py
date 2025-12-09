
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum   

# ---------------------------
# Diagnosis Coding Standards
# ---------------------------
class DiagnosisCoding(BaseModel):
    icd10_enabled: bool = False
    snomed_enabled: bool = False
    # is_primary: bool = False
    # is_clinical: bool = False


# ---------------------------
# Procedure Coding Standards
# ---------------------------
class ProcedureCoding(BaseModel):
    cpt_enabled: bool = False
    hcpcs_enabled: bool = False
    icd10pcs_enabled: bool = False


# ---------------------------
# Laboratory Coding Standards
# ---------------------------

class LoinicPolicyEnum(str, Enum):
    LAB_SUPPLIED = "Lab Supplied LOINC Codes"
    internal_mapping = "Internal LOINC Mapping"

class UnitPolicyEnum(str, Enum):
    UCUM = "Unified Code for Units of Measure"
    other_UNITS = "Other Unit System"

class LaboratoryCoding(BaseModel):
    loinc_policy: Optional[LoinicPolicyEnum] = None         # e.g., "Lab Supplied", "Centralized Mapping"
    unit_policy: Optional[UnitPolicyEnum] = None          # e.g., "UCUM", "Local Units"


# ---------------------------
# Allergy Coding Standards
# ---------------------------
class AllergyCoding(BaseModel):
    rxnorm_enabled: bool = False
    unii_enabled: bool = False
    other_enabled: bool = False


# ---------------------------
# Terminology Update Management
# ---------------------------

class TerminologySourceEnum(str, Enum):
    Monthly = "Monthly"
    Quarterly = "Quarterly"
    ad_hoc = "Ad Hoc (As Needed)"
    

class TerminologyUpdate(BaseModel):
    update_cadence: Optional[TerminologySourceEnum] = None        # e.g., Monthly, Quarterly, Weekly

# ---------------------------
# MASTER Standards Document
# ---------------------------


class FacilityStandardsSchema(BaseModel):
    diagnosis_coding: Optional[DiagnosisCoding] = None
    procedure_coding: Optional[ProcedureCoding] = None
    laboratory_coding: Optional[LaboratoryCoding] = None
    allergy_coding: Optional[AllergyCoding] = None
    terminology_update: Optional[TerminologyUpdate] = None