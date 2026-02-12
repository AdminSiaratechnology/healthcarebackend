from beanie import Document, Link, Indexed
from bson import Binary
from datetime import datetime, timezone,date
from pydantic import Field
from app.accounts.models.user import UserDoc
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.facility.models.facility import Facility
from app.provider.models.providers import Provider
from app.patients.models.patients import PatientDoc
from typing_extensions import Annotated


class ScheduleDoc(Document, AutoDecryptMixin, AutoEncryptMixin):
    # 🔗 Relations
    facility_id: Link[Facility] = Field(..., description="Reference to the associated facility")
    provider_id : Link["Provider"]
    patient_id : Link[PatientDoc] = Field(..., description="Reference to the Patient")
    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None


    # 🔐 Encrypted
    selected_date : Binary | None = None
    shift_time :Binary | None = None
    department : Binary | None = None
    is_create_recurring_shift : Binary | None = None


    # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: datetime | None = None

    status: Annotated[str, Indexed()] = "scheduled"

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "arbitrary_types_allowed": True
    }

    class Settings:
        name = "schedule"
        indexes = [
           
            [("is_deleted", 1), ("facility_id.$id", 1)],
            # Single indexes for frequent queries
            "facility_id",
            "provider_id",
            "status",
            "patient_id",
            "created_by"

            
        ]