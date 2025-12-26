from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone
from pydantic import Field
from app.accounts.models.user import UserDoc
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.patients.models.patients import PatientDoc

class PrescriptionDoc(Document, AutoDecryptMixin, AutoEncryptMixin):
    patient_id: Link["PatientDoc"] | None = None
    medication : Binary 
    dosage : Binary
    frequency : Binary
    route : Binary
    quantity : Binary
    refills : Binary
    instructions : Binary | None = None
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "arbitrary_types_allowed": True
    }

    class Settings:
        name = "prescription"
