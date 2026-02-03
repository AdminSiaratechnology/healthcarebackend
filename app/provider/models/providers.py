from beanie import Document, Link, Indexed
from bson import Binary
from datetime import datetime, timezone
from typing import ClassVar, Set
from pydantic import Field
from app.accounts.models.user import UserDoc
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.encryption.encrypt_mixin import AutoEncryptMixin
from typing import List
from app.facility.models.facility import Facility
from typing_extensions import Annotated

class Provider(Document, AutoDecryptMixin, AutoEncryptMixin):
    # 🔗 Relations

    facility_ids: List[Link[Facility]] | None = None
    primary_facility_id: Link[Facility] | None = None
    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None
    user: Link[UserDoc] | None = None

    # 🔐 Encrypted

    first_name : Binary | None = None
    middle_name : Binary | None = None
    last_name : Binary | None = None
    degree : Binary | None = None
    speciality : Binary | None = None
    subspeciality : Binary | None = None
    npi_no : Binary | None = None
    taxonomy_code : Binary | None = None
    license_no : Binary | None = None
    license_state : Binary | None = None
    dea_no : Binary | None = None
    dea_expiration_date : Binary | None = None
    professional_email : Binary | None = None
    professional_phone : Binary | None = None
    rotation_days : Binary | None = None
    oncall_days : Binary | None = None
    visit_type : Binary | None = None
    billing_location_code : Binary | None = None
    
    profile_pic: str | None = None
    signature: str | None = None

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
        name = "providers"
        indexes = [
            ["created_at", "created_by"],
            [("is_deleted", 1), ("facility_ids.$id", 1)]
            

        ]
        
        
