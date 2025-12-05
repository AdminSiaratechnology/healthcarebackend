from pydantic import BaseModel
from typing import Optional
from enum import Enum


class RoomType(str, Enum):
    Private = "Private"
    Semi = "Semi"
    Multi = "Multi"



class RoomFeatures(BaseModel):
    bathroom: bool = False
    kitchenette: bool = False
    balcony: bool = False
    medical_gas: bool = False
    oxygen: bool = False
    suction: bool = False
    call_system: bool = False



    
class FacilityRoom(BaseModel):
    room_id: Optional[str] = None
    room_type: Optional[RoomType] = None
    wing: Optional[str] = None
    features: Optional[RoomFeatures] = None 
    isolation_room: Optional[bool] = False
    notes: Optional[str] = None
