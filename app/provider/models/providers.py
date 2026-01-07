from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone
from typing import ClassVar, Set
from pydantic import Field
from app.accounts.models.user import UserDoc
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.encryption.encrypt_mixin import AutoEncryptMixin


class Provider(Document, AutoDecryptMixin, AutoEncryptMixin):
    encrypted_fields: ClassVar[Set[str]] = {"profile", "profile_pic", "role"}
    user: Link[UserDoc] | None = None
    role : Binary | None = None
    user_id: str | None = None
    profile: Binary | None = None
    profile_pic: Binary | None = None
    signature: Binary | None = None
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "arbitrary_types_allowed": True
    }


    class Settings:
        name = "providers"
        indexes = ["created_at", "created_by"]
