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
from app.VisitType.models import VisitType # Import VisitType
from typing_extensions import Annotated
from typing import Optional
from pymongo import IndexModel, ASCENDING


class ScheduleDoc(Document):

    # 🔗 Relations
    facility_id: Link[Facility] = Field(..., description="Facility reference")
    provider_id: Link[Provider] = Field(..., description="Provider reference")
    patient_id: Link[PatientDoc] = Field(..., description="Patient reference")
    visit_type: Link[VisitType] | None = None # Add VisitType Link

    # 📅 Core Appointment
    appointment_datetime: datetime = Field(..., description="UTC appointment datetime")

    # 📌 Status
    status: Annotated[str, Indexed()] = Field(
        default="scheduled",
        description="scheduled / completed / cancelled / rescheduled / no_show"
    )

    # 📝 Optional Medical Notes (Encrypt if contains PHI)
    notes: Optional[str] = None

    # ❌ Cancellation
    cancelled_by: Optional[Link[UserDoc]] = None
    cancellation_reason: Optional[str] = None
    cancelled_at: Optional[datetime] = None

    # 🔁 Reschedule
    rescheduled_from: Optional[Link["ScheduleDoc"]] = None

    # 👤 Audit Fields (HIPAA important)
    created_by: Optional[Link[UserDoc]] = None
    updated_by: Optional[Link[UserDoc]] = None

    # 🗑 Soft Delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[Link[UserDoc]] = None

    # ⏱ Check-in / Check-out
    checkin_time: Optional[datetime] = None
    checkout_time: Optional[datetime] = None

    # 🚨 Flags
    reminder_sent: bool = False
    no_show: bool = False

    # 🕒 Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    async def save(self, *args, **kwargs):
        self.updated_at = datetime.now(timezone.utc)
        return await super().save(*args, **kwargs)

    model_config = {
        "arbitrary_types_allowed": True
    }

    class Settings:
        name = "schedules"

        indexes = [

            # 🔍 Fast Lookup Indexes
            "facility_id",
            "provider_id",
            "patient_id",
            "status",
            "created_by",

            # 📅 Provider Calendar Query
            IndexModel(
                [
                    ("provider_id.$id", ASCENDING),
                    ("appointment_datetime", ASCENDING),
                ],
                name="provider_calendar_index"
            ),

            # 🚫 Prevent Double Booking
            IndexModel(
                [
                    ("provider_id.$id", ASCENDING),
                    ("appointment_datetime", ASCENDING),
                ],
                unique=True,
                name="unique_provider_slot"
            ),

            # 📊 Patient History Query
            IndexModel(
                [
                    ("patient_id.$id", ASCENDING),
                    ("appointment_datetime", ASCENDING),
                ],
                name="patient_history_index"
            ),

            # 🗑 Soft Delete Filtering
            IndexModel(
                [
                    ("is_deleted", ASCENDING),
                    ("appointment_datetime", ASCENDING),
                ],
                name="active_schedule_filter"
            ),
        ]

class ProviderAssignmentHistory(Document):
    schedule_id: Link[ScheduleDoc] = Field(..., description="Schedule reference")
    provider_id: Link[Provider] = Field(..., description="Provider reference")
    patient_id: Link[PatientDoc] = Field(..., description="Patient reference")


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
