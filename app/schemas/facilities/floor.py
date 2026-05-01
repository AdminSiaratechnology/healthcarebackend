from pydantic import BaseModel
from typing import Optional


class FloorSchema(BaseModel):
    
    facility_id: Optional[str] = None
    floor_label: Optional[str] = None
    display: Optional[str] = None