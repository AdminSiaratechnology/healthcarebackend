from beanie import Document, Link,Indexed
from bson import Binary
from datetime import datetime, timezone
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility
from typing_extensions import Annotated
from pymongo import ASCENDING

class FacilityFloor(Document, AutoEncryptMixin, AutoDecryptMixin):

    # 🔗 Relations
    facility_id: Link[Facility] 
    created_by: Link[UserDoc]
    deleted_by: Link[UserDoc] | None = None

    # 🔐 Encrypted
    floor_label: Binary | None = None
    display: Binary | None = None

    # 🟢 Searchable (NON-PHI)
    floor_label_search: Annotated[str | None, Indexed()] = None

    # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: datetime | None = None

    # 📌 Status
    status: Annotated[str, Indexed()] = "active"

    # 🕒 Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facility_floors"

        # ✅ Compound indexes
        indexes = [
            # Duplicate floor check per facility
            [
                ("facility_id", ASCENDING),
                ("floor_label_search", ASCENDING),
                ("is_deleted", ASCENDING),
            ],

            # Common filtering
            [
                ("facility_id", ASCENDING),
                ("status", ASCENDING),
            ],

            # Ownership queries (optional but useful)
            [
                ("created_by", ASCENDING),
            ],
        ]