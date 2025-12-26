from pydantic import BaseModel
from typing import Optional
from enum import Enum

class ChargeNursesSchema(BaseModel):
    name : Optional[str] = None
    unit : Optional[str] = None
    phone : Optional[str] = None