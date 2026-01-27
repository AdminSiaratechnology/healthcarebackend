from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility
from beanie import Document, Link, Indexed
from bson import Binary
from datetime import datetime, timezone
from typing_extensions import Annotated


class SecurityDoc(Document, AutoEncryptMixin, AutoDecryptMixin):
    # 🔗 Relations
    facility_id: Link[Facility] = Field(..., description="Reference to the associated facility")
    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None
    
    # 🔐 Encrypted
    phi_export_controls: Binary | None = None  # Serialized JSON of security settings
    breakglass_procedures: Binary | None = None  # Serialized JSON of security settings
    privacy_policies: Binary | None = None  # Serialized JSON of security settings


    # 🔁 Recycle bin support
    is_deleted: Annotated[bool, Indexed()] = False
    
   

    status: Annotated[str, Indexed()] = "active"
    
    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facility_security"
        indexes = [
            [("is_deleted", 1), ("facility_id.$id", 1)],
        ]