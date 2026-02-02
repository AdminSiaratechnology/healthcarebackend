from beanie import Document, Link, Indexed
from bson import Binary
from datetime import datetime, timezone
from typing import ClassVar, Set
from pydantic import Field
from app.accounts.models.user import UserDoc
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.facility.models.facility import Facility
from app.provider.models.providers import Provider
from app.facility.models.beds import Beds
from typing_extensions import Annotated

class PatientDoc(Document, AutoDecryptMixin, AutoEncryptMixin):
    # 🔗 Relations
    facility_id: Link[Facility] = Field(..., description="Reference to the associated facility")
    bed_id : Link[Beds]
    provider_id : Link["Provider"] | None = None
    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None
    user_id : Link[UserDoc] | None = None

    # 🔐 Encrypted
    personal_information : Binary | None = None
    admisson_information : Binary | None = None
    address_information : Binary | None = None
    insurance_information : Binary | None = None
    emergency_contact_information : Binary | None = None


    # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: datetime | None = None

    status: Annotated[str, Indexed()] = "active"

    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "arbitrary_types_allowed": True
    }

    class Settings:
        name = "patients"
        indexes = [
           
            [("is_deleted", 1), ("facility_id.$id", 1)],
            
        ]
