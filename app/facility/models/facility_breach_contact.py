from beanie import Document, Link, Indexed
from bson import Binary
from datetime import datetime, timezone
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility
from typing_extensions import Annotated

class BrachResponseContactDocs(Document, AutoEncryptMixin, AutoDecryptMixin):

    # 🔗 Relations
    facility_id: Link[Facility] | None = None
    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None



    # 🔐 Encrypted
    name : Binary | None = None
    Role : Binary | None = None
    phone : Binary | None = None
    email : Binary | None = None

     
    # 🟢 Searchable (NON-PHI)
    name_search : Annotated[str | None, Indexed()] = None
    phone_search : Annotated[str | None, Indexed()] = None
    email_search : Annotated[str | None, Indexed()] = None


    # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: datetime | None = None

    status: Annotated[str, Indexed()] = "active"
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facility_breach_contacts"
        indexes = [
            [("facility_id.$id", 1), ("name_search", 1)],
            [("facility_id.$id", 1), ("phone_search", 1)],
            [("facility_id.$id", 1), ("email_search", 1)],
            [("is_deleted", 1), ("facility_id.$id", 1)],
        ]