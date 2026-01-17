from typing_extensions import Annotated
from beanie import Document, Indexed, Link
from bson import Binary
from datetime import datetime, timezone

from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility

class CampusBlock(Document, AutoEncryptMixin, AutoDecryptMixin):
    # 🔐 Encrypted
    block_code: Binary | None = None
    block_name: Binary | None = None

    # 🟢 Plain searchable (NON-PHI)
    block_name_search: Annotated[str, Indexed()]

    facility_id: Link[Facility]

    # 🔁 Recycle bin support
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: datetime | None = None
    deleted_by: Link[UserDoc] | None = None

    status: Annotated[str, Indexed()] = "active"

    created_by: Link[UserDoc]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "campus_blocks"
        indexes = [
            [("facility_id.$id", 1), ("block_name_search", 1)],
            [("is_deleted", 1), ("facility_id.$id", 1)],
        ]
