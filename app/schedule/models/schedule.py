from beanie import Document, Link, Indexed
from bson import Binary
from datetime import datetime, timezone, date, time
from pydantic import Field
from app.accounts.models.user import UserDoc
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.facility.models.facility import Facility
from app.provider.models.providers import Provider
from app.patients.models.patients import PatientDoc
from typing_extensions import Annotated
from typing import Optional
from pymongo import IndexModel, ASCENDING


class ScheduleDoc(Document, AutoDecryptMixin, AutoEncryptMixin):
    # 🔗 Relations
    facility_id: Link[Facility] = Field(..., description="Facility reference")
    provider_id: Link[Provider] = Field(..., description="Provider reference")
    patient_id: Link[PatientDoc] = Field(..., description="Patient reference")

    created_by: Optional[Link[UserDoc]] = None
    deleted_by: Optional[Link[UserDoc]] = None
    rescheduled_from: Optional[Link["ScheduleDoc"]] = None

    # 📅 Scheduling
    schedule_date: date
    slot_time: time

    # 🔐 Encrypted Fields
    department: Optional[Binary] = None
    is_create_recurring_shift: Optional[Binary] = None

    # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: Optional[datetime] = None

    # 📌 Status
    status: Annotated[str, Indexed()] = "scheduled"

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    async def save(self, *args, **kwargs):
        self.updated_at = datetime.now(timezone.utc)
        return await super().save(*args, **kwargs)

    model_config = {
        "arbitrary_types_allowed": True
    }

    class Settings:
        name = "schedule"
        indexes = [
            [("is_deleted", ASCENDING), ("facility_id.$id", ASCENDING)],
            "facility_id",
            "provider_id",
            "status",
            "patient_id",
            "created_by",
            "rescheduled_from",
            [("provider_id.$id", ASCENDING), ("schedule_date", ASCENDING)],
            IndexModel(
                [
                    ("provider_id.$id", ASCENDING),
                    ("schedule_date", ASCENDING),
                    ("slot_time", ASCENDING),
                ],
                unique=True,
                name="unique_provider_slot"
            )
        ]



class ProviderAssignmentHistory(Document):
    schedule_id: Link[ScheduleDoc] = Field(..., description="Schedule reference")
    provider_id: Link[Provider] = Field(..., description="Provider reference")

    assigned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    unassigned_at: Optional[datetime] = None

    class Settings:
        name = "provider_assignment_history"
        indexes = [
            IndexModel(
                [("schedule_id.$id", ASCENDING), ("unassigned_at", ASCENDING)],
                name="schedule_active_provider_lookup"
            )
        ]
