from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility
from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone


class WorkflowDoc(Document, AutoEncryptMixin, AutoDecryptMixin):
    facility_id: Link[Facility] = Field(..., description="Reference to the associated facility")
    admission_workflow: Binary | None = None  # Serialized JSON of workflow settings
    documentation_workflow: Binary | None = None  # Serialized JSON of workflow settings
    billing_workflow: Binary | None = None  # Serialized JSON of workflow settings
    clinical_protocols: Binary | None = None  # Serialized JSON of workflow settings
    vaccine_rules: Binary | None = None  # Serialized JSON of workflow settings

    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facility_workflow"