from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone
from typing import ClassVar, Set
from pydantic import Field
from app.accounts.models.user import UserDoc
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.encryption.encrypt_mixin import AutoEncryptMixin

class Admin(Document, AutoDecryptMixin, AutoEncryptMixin):
    # which fields this model encrypts / decrypts automatically (not a Pydantic field)
    encrypted_fields: ClassVar[Set[str]] = {"profile"}

    user: Link[UserDoc] | None = None
    user_id: str | None = None
    # store encrypted profile as Binary instead of plain AdminProfile
    profile: Binary | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "admins"

    model_config = {
        "arbitrary_types_allowed": True
    }
