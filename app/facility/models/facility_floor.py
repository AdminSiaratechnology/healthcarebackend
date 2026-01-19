from beanie import Document, Link,Indexed
from bson import Binary
from datetime import datetime, timezone
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility
from typing_extensions import Annotated


class FacilityFloor(Document, AutoEncryptMixin, AutoDecryptMixin):
    floor_label: Binary | None = None
    # 🟢 Plain searchable (NON-PHI)
    floor_label_search: Annotated[str, Indexed()]
    display : Binary | None = None
    facility_id: Link[Facility] | None = None
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facility_floors"