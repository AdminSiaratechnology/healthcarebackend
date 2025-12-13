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
    facility_id: str
    first_name:  Optional[str] = None
    middle_name :  Optional[str] = None
    last_name :  Optional[str] = None
    preferred_name :  Optional[str] = None
    maiden_name:  Optional[str] = None
    birth_place: Optional[str] = None
    dob : date
    gender : Optional[genderEnum] = None
    race : Optional[RaceEnum] = None
    primary_language: Optional[Primary_language] = None
    marital_status: Optional[Marital_status] = None
    religion: Optional[str] = None


class ContactInformation(BaseModel):
    phone_number : Optional[str] = None
    email : Optional[EmailStr] = None
    password : Optional[str] = None
    
