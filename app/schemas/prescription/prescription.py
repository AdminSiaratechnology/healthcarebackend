from pydantic import BaseModel
from typing import Optional
from enum import Enum

class frequencyEnum(str, Enum):
    OnceDaily = "Once Daily"
    TwiceDaily = "Twice Daily"
    ThreeTimesDaily = "Three Times Daily"
    FourTimesDaily = "Four Times Daily"
    AsNeeded = "As Needed"
    Every4Hours = "Every 4 Hours"
    Every6Hours = "Every 6 Hours"
    Every8Hours = "Every 8 Hours"
    Every12Hours = "Every 12 Hours"


class RouteEnum(str, Enum):
    Oral = "Oral"
    Topical = "Topical"
    Injection = "Injection"
    Inhalation = "Inhalation"
    Sublingual = "Sublingual"
    Transdermal = "Transdermal"

class PrescriptionSchema(BaseModel):
    medication : str
    dosage : str
    frequency : frequencyEnum
    route: RouteEnum
    quantity  : int
    refills : int
    instructions : Optional[str] = None



