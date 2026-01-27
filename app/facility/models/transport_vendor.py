from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility
from beanie import Document, Link, Indexed
from bson import Binary
from datetime import datetime, timezone
from typing_extensions import Annotated

class TransportVendorDocs(Document, AutoEncryptMixin, AutoDecryptMixin):
    # 🔗 Relations
    facility_id: Link[Facility] = Field(..., description="Reference to the associated facility")
    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None

    # 🔐 Encrypted
    vendor_name: Binary | None = None
    contact_number : Binary | None = None
    

     # 🟢 Plain searchable (NON-PHI)
    vendor_name_search: Annotated[str, Indexed()]
    vendor_contact_no_search : Annotated[str, Indexed()]

    # 🔁 Recycle bin support
    is_deleted: Annotated[bool, Indexed()] = False
    
   

    status: Annotated[str, Indexed()] = "active"

    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facility_transportVendor"
        indexes = [
            [("facility_id.$id", 1), ("vendor_name_search", 1)],
            [("facility_id.$id", 1), ("vendor_contact_no_search", 1)],
            [("is_deleted", 1), ("facility_id.$id", 1)],
        ]
