from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility
from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone


class SecurityDoc(Document, AutoEncryptMixin, AutoDecryptMixin):
    facility_id: Link[Facility] = Field(..., description="Reference to the associated facility")
    user_roles_access: Binary | None = None  # Serialized JSON of security settings
    authentication_sessions: Binary | None = None  # Serialized JSON of security settings
    phi_export_controls: Binary | None = None  # Serialized JSON of security settings
    breakglass_procedures: Binary | None = None  # Serialized JSON of security settings
    privacy_policies: Binary | None = None  # Serialized JSON of security settings
    breach_response_contacts: Binary | None = None  # Serialized JSON of security settings
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facility_security"