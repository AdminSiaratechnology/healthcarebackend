from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.clinicalmonitoring.models.category import CategoryDoc



class SubcategoryDoc(Document, AutoEncryptMixin, AutoDecryptMixin):
    category_id: Link[CategoryDoc]
    name : Binary
    description : Binary | None = None
    content : Binary | None = None
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "template_subcategory"
