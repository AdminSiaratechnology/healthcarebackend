from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone

from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.facility.models.facility import Facility
from app.provider.models.providers import Provider


class Practice(Document,AutoEncryptMixin, AutoDecryptMixin):
    provider_id : Link[Provider] | None = None
    facility_ids: list[Link[Facility]] = []
    primary_facility_id: Link[Facility] | None = None
    assigned_practice: Binary | None = None
    rotation_days : Binary | None = None
    on_calls_days : Binary | None = None
    default_visit_type : Binary | None = None
    billing_location_code : Binary | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "practices"
