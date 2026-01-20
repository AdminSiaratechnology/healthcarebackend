from beanie import Document, Link, Indexed
from bson import Binary
from datetime import datetime, timezone
from typing_extensions import Annotated
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility



class Pharmacies(Document, AutoEncryptMixin, AutoDecryptMixin):
    # 🔗 Relations
    facility_id: Link[Facility] = Field(..., description="Reference to the associated facility")
    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None

    # 🔐 Encrypted
    pharmacy_name: Binary | None = None
    phone: Binary | None = None
    address: Binary | None = None
    fax: Binary | None = None
    after_hours_phone: Binary | None = None
    contract_file_id: Binary | None = None
    delivery_schedule: Binary | None = None
    

    # 🟢 Searchable (NON-PHI)
    pharmacy_name_search: Annotated[str | None, Indexed()] = None

    # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: datetime | None = None

    status: Annotated[str, Indexed()] = "active"

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "pharmacies"
        indexes = [
            [("facility_id.$id", 1), ("pharmacy_name_search", 1)],
            [("is_deleted", 1), ("facility_id.$id", 1)],
            
        ]