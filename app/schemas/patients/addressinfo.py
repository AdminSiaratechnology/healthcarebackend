from pydantic import BaseModel,EmailStr
from typing import Optional


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



class PatientAddressSchema(BaseModel):

    current_address : Optional[CurrentAddress] = None
    previous_address : Optional[PreviousAddress] = None
