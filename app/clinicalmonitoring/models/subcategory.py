from beanie import Document, Link, Indexed
from bson import Binary
from datetime import datetime, timezone
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.clinicalmonitoring.models.category import CategoryDoc
from typing_extensions import Annotated


class SubcategoryDoc(Document, AutoEncryptMixin, AutoDecryptMixin):
    # 🔗 Relations
    category_id: Link[CategoryDoc]
    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None

    # 🔐 Encrypted
    name : Binary
    # description : Binary | None = None
    # content : Binary | None = None

    # 🟢 Plain searchable (NON-PHI)
    name_search: Annotated[str, Indexed()]

      # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: datetime | None = None
    status: Annotated[str, Indexed()] = "active"

    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "template_subcategory"
        indexes = [
            # 🔥 Most common listing query
            [("is_deleted", 1), ("status", 1)],

            # 🔎 Fast search
            "name_search",

            # Optional (agar user wise filter chahiye)
            "created_by",
        ]
