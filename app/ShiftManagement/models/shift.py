from beanie import Document, Link, Indexed
from bson import Binary
from datetime import datetime, timezone
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility
from typing_extensions import Annotated

class ShiftManagementDocs(Document, AutoEncryptMixin, AutoDecryptMixin):

    # 🔗 Relations
    facility_ids: list[Link[Facility]] = Field(default_factory=list) 
    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None


    # 🔐 Encrypted

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
    
    # 🟢 Plain searchable (NON-PHI)
    name_search: Annotated[str, Indexed()]

    # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: datetime | None = None
    status: Annotated[str, Indexed()] = "active"
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "shift_managements"
        indexes = [
        [("facility_id.$id", 1), ("block_name_search", 1)],
        # 🔥 Primary filter index
        [("is_deleted", 1), ("status", 1), ("facility_ids.$id", 1)],

        # ⚡ Optional quick facility lookup
        [("facility_ids.$id", 1)],

        # 📌 Optional (only if used alone often)
        [("status", 1)],
    ]