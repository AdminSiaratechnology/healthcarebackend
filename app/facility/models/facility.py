
from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone
from typing import ClassVar
from pydantic import Field, ConfigDict
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin



class Facility(Document, AutoEncryptMixin, AutoDecryptMixin):
    basic: Binary | None = None
   
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

   
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facilities"
