from pydantic import BaseModel
from typing import Optional
from enum import Enum




class FacilityStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class FacilityType(str, Enum):
    HOSPITAL = "hospital"
    CLINIC = "clinic"
    URGENT_CARE = "urgent_care"
    LAB = "lab"
    OTHER = "other"


class BasicInfo(BaseModel):
    facility_name: str
    facility_type: Optional[FacilityType] = None
    main_phone: Optional[str] = None
    facility_code: Optional[str] = None
    fax: Optional[str] = None
    general_email:  Optional[str] = None
    website_url: Optional[str] = None
    timezone: Optional[str] = None
    operating_hours: Optional[str] = None


class AddressInfo(BaseModel):
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None



class FacilityCreate(BaseModel):
    facility_name : str
    facility_status: Optional[FacilityStatus] = FacilityStatus.ACTIVE
    basic_info: BasicInfo
    address_info: AddressInfo




# ------------------------------------------------- BrandingDoc, ContactsDoc, AddressDoc, BasicDoc, StructureDoc, RoomsDoc, RoomsBedsDoc, PartnersDoc, WorkstationsDoc, InteroperabilityDoc, RegulatoryDoc, KeyContactsDoc ---------------------------------------------------

# These schemas have been removed and their fields integrated into the Facility model directly.
# They are retained here as comments for reference.

class ColorScheme(BaseModel):
    primary_color : Optional[str] = None
    secondary_color : Optional[str] = None
    accent_color : Optional[str] = None
    


class  BrandGuidelines(BaseModel):
    brand_notes: Optional[str] = None
    

class BrandingInfo(BaseModel):
    logo: Optional[str] = None
    color_scheme: Optional[ColorScheme] = None
    brand_guidelines: Optional[BrandGuidelines] = None


# ---------------------------------------------------------------------------------- Schema End -------------------------------------------------------------------------------    



# -------------------------------------------------- Structure ---------------------------------------------------


class CampusBlock(BaseModel):
    block_code: Optional[str] = None
    block_name: Optional[str] = None


class Floors(BaseModel):
    floor_label: Optional[int] = None
    


class Departments(BaseModel):
    code : Optional[str] = None
    name : Optional[str] = None
    type: Optional[str] = None
   

class StructureInfo(BaseModel):
    campus_blocks: Optional[list[CampusBlock]] = None
    floors: Optional[list[Floors]] = None
    departments: Optional[list[Departments]] = None
    description: Optional[str] = None


# -------------------------------------------------- End Structure ---------------------------------------------------




# -------------------------------------------------- Rooms & Beds ---------------------------------------------------



class RoomType(str, Enum):
    Private = "Private"
    Semi = "Semi"
    Multi = "Multi"
    
class RoomConfiguration(BaseModel):
    room_id: Optional[str] = None
    room_type: Optional[RoomType] = None
    wing: Optional[str] = None



# -------------------------------------------------- End Rooms & Beds ---------------------------------------------------