from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility


class BrachResponseContactDocs(Document, AutoEncryptMixin, AutoDecryptMixin):
    facility_id: Link[Facility] | None = None
    name : Binary | None = None
    Role : Binary | None = None
    phone : Binary | None = None
    email : Binary | None = None
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facility_breach_contacts"