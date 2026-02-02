from pydantic import BaseModel,EmailStr
from typing import Optional
from datetime import date
from enum import Enum


class genderEnum(str, Enum):
    Male = "Male"
    Female = "Female"
    Other = "Other"


class RaceEnum(str, Enum):
    caucasian = "Caucasian"
    hispanic = "Hispanic"
    african_america = "African America"
    asian = "Asian"
    native_american = "Native American"
    other = "Other"


class Primary_language(str, Enum):
    english = "English"    
    spanish = "Spanish"
    french = "French"
    chinese = "Chinese"
    other = "Other"


class Marital_status(str, Enum):
    single = "Single"
    married = "Married"
    divorced = "Divorced"
    widowd = "Widowed"

class PersonalInfo(BaseModel):
   
    first_name:  Optional[str] = None
    middle_name :  Optional[str] = None
    last_name :  Optional[str] = None
    preferred_name :  Optional[str] = None
    maiden_name:  Optional[str] = None
    birth_place: Optional[str] = None
    dob : date = None
    gender : Optional[genderEnum] = None
    race : Optional[RaceEnum] = None
    primary_language: Optional[Primary_language] = None
    marital_status: Optional[Marital_status] = None
    religion: Optional[str] = None


class ContactInformation(BaseModel):
    phone_number : Optional[str] = None
    email : Optional[EmailStr] = None
    password : Optional[str] = None


class AdmissionTypeEnum(str, Enum):
    Elective = "Elective"
    Emergency = "Emergency"
    transfer = "Transfer"
    Other = "Other"


class PatientStatus(str, Enum):
    Active = "Active"
    Inactive = "Inactive"
    Discharged = "Discharged"
    Transferred = "Transferred"


class AdmittedForm(str, Enum):
    Home = "Home"
    Hospital = "Hospital"
    NursingHome = "Nursing Home"
    Other_facility = "Other Facility"


class Admission(BaseModel):
    admission_date : date = None
    original_admission_date : date = None
    admissio_location : Optional[str] = None
    resident_no : Optional[str] = None
    admission_type : AdmissionTypeEnum
    patient_status : PatientStatus = PatientStatus.Active 
    admitted_form : AdmittedForm
    from_date : date
    to_date : date




class CurrentAddress(BaseModel):
    street_address : Optional[str] = None
    city : Optional[str] = None
    state : Optional[str] = None
    zipcode : Optional[int] = None
    country : Optional[str] = None


class PreviousAddress(BaseModel):
    street_address : Optional[str] = None
    city : Optional[str] = None
    state : Optional[str] = None
    zipcode : Optional[int] = None
    country : Optional[str] = None



# -------------------------------- Insurance ----------------------------------------------



class medicareInformation(BaseModel):
    beneficiary_id : Optional[str] = None
    primary_payer : Optional[str] = None
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


# -------------------------------- Emergency Contact & Physician ----------------------------------------------

class EmergencyContact(BaseModel):
    name : Optional[str] = None
    relationship : Optional[str] = None
    phone_number : Optional[str] = None

   
class SecondaryEmergencyContact(BaseModel):
    name : Optional[str] = None
    relationship : Optional[str] = None
    phone_number : Optional[str] = None
    
class PatientSchema(BaseModel):
    provider_id : str
    bed_id :str
    personal_information : Optional[PersonalInfo] = None
    contact_information : Optional[ContactInformation] = None
    admission_information : Optional[Admission] = None
    current_address : Optional[CurrentAddress] = None
    previous_address : Optional[PreviousAddress] = None
    medicare_information : Optional[medicareInformation] = None
    medicare_advantage : Optional[MedicareAdvantage] = None
    primary_secondary_insurance : Optional[PrimarySecondaryInsurance] = None
    emergency_contact : Optional[EmergencyContact] = None
    secondary_emergency_contact : Optional[SecondaryEmergencyContact] = None

    