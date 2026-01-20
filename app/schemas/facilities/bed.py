from pydantic import BaseModel
from typing import Optional
from enum import Enum

class statusEnum(str, Enum):
    Vacant = "Vacant"
    Occupied = "Occupied"
    Reserved = "Reserved"
    Maintenance = "Maintenance"

class Bed(BaseModel):
    
    room_id: Optional[str] = None
    bed_number: Optional[str] = None
    designation: Optional[str] = None
    bed_status : Optional[statusEnum] = statusEnum.Vacant
    bariatric: Optional[bool] = False
    move_policy: Optional[str] = None