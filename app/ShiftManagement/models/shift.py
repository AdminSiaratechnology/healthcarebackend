from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility


class ShiftManagementDocs(Document, AutoEncryptMixin, AutoDecryptMixin):
    name: Binary | None = None
    shift: Binary | None = None
    start_time: Binary | None = None
    end_time: Binary | None = None
    shift_type: Binary | None = None
    break_duration: Binary | None = None
    minumum_staff_required: Binary | None = None
    maximum_staff_allowed: Binary | None = None
    priority: Binary | None = None
    required_role: Binary | None = None
    active_days: Binary | None = None
    description: Binary | None = None
    facility_ids: list[Link[Facility]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Link[UserDoc] | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "shift_managements"