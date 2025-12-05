from pydantic import BaseModel
from typing import Optional

class ImagingCenterSchema(BaseModel):
    center_name: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    turnaround_time: Optional[str] = None
    transport_notes: Optional[str] = None