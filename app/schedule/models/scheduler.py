from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone,date
from pydantic import Field
from app.accounts.models.user import UserDoc
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.facility.models.facility import Facility
from app.provider.models.providers import Provider

class SchedulerDoc(Document, AutoDecryptMixin, AutoEncryptMixin):
    provider_id : Link["Provider"]
    facility_id: Link["Facility"] 
    selected_date : Binary | None = None
    shift_time :Binary | None = None
    department : Binary | None = None
    is_create_recurring_shift : Binary | None = None
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "arbitrary_types_allowed": True
    }

    class Settings:
        name = "scheduler"