from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone

from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility

class RegulatoryInfoDoc(Document, AutoEncryptMixin, AutoDecryptMixin):
    facility_id: Link[Facility] = Field(..., description="Reference to the associated facility")
    state_license: Binary | None = None
    federal_certification: Binary | None = None
    accreditations: Binary | None = None  # Serialized list of accreditations
    onc_certification: Binary | None = None
    state_reporting_identifier: Binary | None = None
   
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "regulatory_info"