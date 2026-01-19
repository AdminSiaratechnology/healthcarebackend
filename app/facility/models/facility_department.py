from beanie import Document, Link, Indexed
from bson import Binary
from datetime import datetime, timezone
from typing_extensions import Annotated
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility


class FacilityDepartment(Document, AutoEncryptMixin, AutoDecryptMixin):
    # 🔗 Relations
    facility_id: Link[Facility] | None = None
    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None

    # 🔐 Encrypted
    code : Binary | None = None
    department_name: Binary | None = None
    type: Binary | None = None
    description: Binary | None = None

    # 🟢 Searchable (NON-PHI)
    code_search: Annotated[str | None, Indexed()] = None
    department_search : Annotated[str | None, Indexed()] = None
    type_search : Annotated[str | None, Indexed()] = None
    
    # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: datetime | None = None

    # 📌 Status
    status: Annotated[str, Indexed()] = "active"

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facility_departments"
        indexes = [
            [("facility_id.$id", 1), ("department_search", 1)],
            [("is_deleted", 1), ("facility_id.$id", 1)],
            
        ]