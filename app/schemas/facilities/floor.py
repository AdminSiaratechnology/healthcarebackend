from pydantic import BaseModel
from typing import Optional


class FloorSchema(BaseModel):
    
    floor_label: Optional[str] = None
    display: Optional[str] = None