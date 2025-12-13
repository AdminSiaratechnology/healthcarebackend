from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.provider.models.providers import Provider


class clinical(Document, AutoDecryptMixin, AutoEncryptMixin):
    provider_id : Link[Provider] | None = None
    default_note_template : Binary | None = None
    medications : Binary | None = None
    lab_tests : Binary | None = None
    orders : Binary | None = None
    statement : Binary | None = None
    work_flow_automation : Binary | None = None
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "clinical"

