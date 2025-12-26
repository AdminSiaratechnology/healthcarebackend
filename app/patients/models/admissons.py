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


class PatientAdmissionDoc(Document, AutoDecryptMixin, AutoEncryptMixin):
    patient_id : Link[PatientDoc]
    admission_date : Binary | None = None
    room_id : Link[FacilityRooms]
    bed_id : Link[Beds]
    admission_location : Binary | None = None
    resident_number : Binary | None = None
    admission_type : Binary | None = None
    status : Binary | None = None
    admitted_form : Binary | None = None
    from_date : Binary | None = None
    to_date : Binary | None = None
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "arbitrary_types_allowed": True
    }

    class Settings:
        name = "patients_admissions"
