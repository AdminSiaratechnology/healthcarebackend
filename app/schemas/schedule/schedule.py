from pydantic import BaseModel
from typing import Optional
from enum import Enum
from datetime import date,time



    
class ScheduleSchema(BaseModel):
    facility_id : str
    provider_id : str
    patient_id : str
    schedule_date :date
    slot_time : time
    