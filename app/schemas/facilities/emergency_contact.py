from pydantic import BaseModel
from typing import Optional
from enum import Enum

class emergency_contact_Schema(BaseModel):
    role : Optional[str] = None
    phone : Optional[str] = None
    after_hour : bool = False


