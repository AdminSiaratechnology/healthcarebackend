from pydantic import BaseModel
from typing import Optional
from enum import Enum
from datetime import date,time


class ShiftTime(BaseModel):
    start_time: time
    end_time: time

class DepartmentEnum(str, Enum):
    Hospitalist = "Hospitalist"    
    Emergency = "Emergency"
    Cardiology = "Cardiology"
    Orthopedics = "Orthopedics"
    Pediatrics = "Pediatrics"
    Surgery = "Surgery"
    ICU = "ICU"
    Radiology = "Radiology"

    
class ScheduleSchema(BaseModel):
    provider_id : str
    facility_id : str
    selected_date :date
    shift_time : ShiftTime
    department : DepartmentEnum 
    is_create_recurring_shift : bool = True
   
