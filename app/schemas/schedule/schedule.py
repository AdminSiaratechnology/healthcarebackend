from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from enum import Enum, IntEnum
from datetime import date,time,datetime, timezone



    

class SlotDurationEnum(IntEnum):
    MIN_15 = 15
    MIN_30 = 30


class PatientScheduleItem(BaseModel):
    patient_id: str
    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional appointment notes"
    )

class ScheduleSchema(BaseModel):
    facility_id: str
    provider_id: str
    start_datetime: datetime
    slot_duration_minutes: SlotDurationEnum
    patients: List[PatientScheduleItem]
    @field_validator("start_datetime")
    def must_be_future_utc(cls, value):
        if value.tzinfo is None:
            raise ValueError("Datetime must include timezone (UTC required)")
        if value <= datetime.now(timezone.utc):
            raise ValueError("Appointment must be in the future")
        return value

    @field_validator("patients")
    def validate_patient_list(cls, v):
        if not v:
            raise ValueError("At least one patient required")
        return v