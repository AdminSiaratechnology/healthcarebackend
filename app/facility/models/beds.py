from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone

from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms

class Beds(Document, AutoEncryptMixin, AutoDecryptMixin):
    facility_id: Link[Facility] | None = None
    bed_id: Binary = Field(..., description="Unique identifier for the bed")
    room_id: Link[FacilityRooms] | None = None
    designation : Binary | None = None
    status : Binary | None = None
    bariatric : Binary | None = None
    last_sanitized : datetime | None = None
    bed_policy : Binary | None = None
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "beds"
