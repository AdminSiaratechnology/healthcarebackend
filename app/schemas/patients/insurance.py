from pydantic import BaseModel,EmailStr
from typing import Optional

class medicareInformation(BaseModel):
    beneficiary_id : Optional[str] = None
    primary_payer : Optional[str] = None
    partd_policy : Optional[str] = None
    partd_policy : Optional[str] = None
    medicare_parta : bool = False
    medicare_partb : bool = False
    medicaid_number : Optional[str] = None


class MedicareAdvantage(BaseModel):
    medicare_advantage_name : Optional[str] = None
    policy_number : Optional[str] = None


class PrimarySecondaryInsurance(BaseModel):
    primary_insurance_cmp : Optional[str] = None
    secondary_provider_name : Optional[str] = None
    primary_policy_no : Optional[str] = None
    secondary_policy_no : Optional[str] = None
    case_manager : Optional[str] = None
    authorization_no : Optional[str] = None



class InsuranceSchema(BaseModel):
    medicare_information : Optional[medicareInformation] = None
    medicare_advantage : Optional[MedicareAdvantage] = None
    primary_secondary_insurance : Optional[PrimarySecondaryInsurance] = None