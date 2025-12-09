from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility
from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone

class QualityDoc(Document, AutoEncryptMixin, AutoDecryptMixin):
    facility_id: Link[Facility] = Field(..., description="Reference to the associated facility")
    enable_mds_reporting: Binary | None = None
    enable_quality_measure: Binary | None = None
    enable_infection_control_tracking: Binary | None = None
    fall_risk_program: Binary | None = None
    quality_reporting: Binary | None = None
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "quality"