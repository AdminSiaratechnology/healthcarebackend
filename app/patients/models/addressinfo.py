from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone
from typing import ClassVar, Set
from pydantic import Field
from app.accounts.models.user import UserDoc
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.patients.models.patients import PatientDoc
from app.facility.models.facility_rooms import FacilityRooms
from app.facility.models.beds import Beds

class PatientAddressInfoDoc(Document, AutoDecryptMixin, AutoEncryptMixin):
    patient_id : Link[PatientDoc]
    current_address : Binary | None = None
    previous_address : Binary | None = None
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "arbitrary_types_allowed": True
    }

    class Settings:
        name = "patients_address"
