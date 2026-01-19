from beanie import Document, Link,Indexed
from bson import Binary
from datetime import datetime, timezone
from typing_extensions import Annotated
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility
from app.facility.models.facility_floor import FacilityFloor


class FacilityRooms(Document, AutoEncryptMixin, AutoDecryptMixin):
    # 🔗 Relations
    facility_id: Link[Facility] | None = None
    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None

    # 🔐 Encrypted
    room_number: Binary | None = None
    room_type: Binary | None = None
    floor : Link[FacilityFloor] | None = None
    wing : Binary | None = None
    room_features: Binary | None = None
    isolation_room: Binary | None = None
    notes: Binary | None = None
    

    # 🟢 Searchable (NON-PHI)
    room_no_search: Annotated[str | None, Indexed()] = None
    room_type_search :  Annotated[str | None, Indexed()] = None


    # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: datetime | None = None

    status: Annotated[str, Indexed()] = "active"


    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facility_rooms"
        indexes = [
            [("facility_id.$id", 1), ("room_no_search", 1)],
            [("facility_id.$id", 1), ("room_type_search", 1)],
            [("is_deleted", 1), ("facility_id.$id", 1)],
            
        ]