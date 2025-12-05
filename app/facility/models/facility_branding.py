from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone
from pydantic import Field, ConfigDict
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility

class FacilityBranding(Document, AutoEncryptMixin, AutoDecryptMixin):
    logo: Binary | None = None
    primary_color : Binary | None = None
    secondary_color : Binary | None = None
    accent_color : Binary | None = None
    brand_notes: Binary | None = None
    facility_id: Link["Facility"] | None = None
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facility_brandings"