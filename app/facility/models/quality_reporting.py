from beanie import Document, Link, Indexed  
from bson import Binary
from datetime import datetime, timezone
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility
from typing_extensions import Annotated


class QualityReporting(Document, AutoEncryptMixin, AutoDecryptMixin):
    # 🔗 Relations
    facility_id: Link[Facility] = Field(..., description="Reference to the associated facility")
    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None

    # 🔐 Encrypted
    organization_name :Binary | None = None
    reporting_cadence :Binary | None = None

    # 🟢 Searchable (NON-PHI)
    organization_name_search : Annotated[str | None, Indexed()] = None

   
    # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: datetime | None = None

    status: Annotated[str, Indexed()] = "active"

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "quality_reporting"
        indexes = [
            [("facility_id.$id", 1), ("organization_name_search", 1)],
            [("is_deleted", 1), ("facility_id.$id", 1)],
        ]
