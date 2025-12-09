from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility
from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone

class StandardsDoc(Document, AutoEncryptMixin, AutoDecryptMixin):
    facility_id: Link[Facility] = Field(..., description="Reference to the associated facility")
    diagnosis_coding: Binary | None = None  # Serialized JSON of standards settings
    procedure_coding: Binary | None = None  # Serialized JSON of standards settings
    laboratory_coding: Binary | None = None  # Serialized JSON of standards settings
    allergy_coding: Binary | None = None  # Serialized JSON of standards settings
    terminology_update: Binary | None = None  # Serialized JSON of standards settings

    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facility_standards"