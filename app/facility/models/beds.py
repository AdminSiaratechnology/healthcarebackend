from beanie import Document, Link,Indexed
from bson import Binary
from datetime import datetime, timezone
from typing_extensions import Annotated
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms

class Beds(Document, AutoEncryptMixin, AutoDecryptMixin):

    # 🔗 Relations

    facility_id: Link[Facility] | None = None
    room_id: Link[FacilityRooms] | None = None
    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None

    # 🔐 Encrypted
    bed_number: Binary = Field(..., description="Unique identifier for the bed")
    designation : Binary | None = None
    bed_status : Binary | None = None
    bariatric : Binary | None = None
    # last_sanitized : datetime | None = None
    bed_policy : Binary | None = None

    
    # 🟢 Searchable (NON-PHI)

    bed_no_search: Annotated[str | None, Indexed()] = None
    bed_status_search:  Annotated[str | None, Indexed()] = None

    # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: datetime | None = None

    status: Annotated[str, Indexed()] = "active"

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "beds"
        indexes = [
            [("facility_id.$id", 1), ("bed_no_search", 1)],
            [("facility_id.$id", 1), ("bed_status_search", 1)],
            [("is_deleted", 1), ("facility_id.$id", 1)],

        ]
        
       