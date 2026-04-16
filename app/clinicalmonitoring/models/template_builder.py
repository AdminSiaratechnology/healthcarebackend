from beanie import Document, Link, Indexed
from bson import Binary
from datetime import datetime, timezone
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc
from app.encryption.encrypt_mixin import AutoEncryptMixin
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.clinicalmonitoring.models.subcategory import SubcategoryDoc
from app.patients.models.patients import PatientDoc
from app.facility.models.facility import Facility
from app.provider.models.providers import Provider
from typing_extensions import Annotated

class TemplateBuilderDoc(Document, AutoEncryptMixin, AutoDecryptMixin):

    # 🔗 Relations
    sub_category_ids: list[Link[SubcategoryDoc]] = Field(default_factory=list) 
    patient_id : Link[PatientDoc] | None = None
    provider_id : Link[Provider] | None = None
    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None


    # 🔐 Encrypted
    template_name : Binary
    short_name : Binary | None = None
    discipline : Binary | None = None


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
        name = "template_builder"
        indexes = [
            # 🔥 Most common listing query
            [("is_deleted", 1), ("status", 1)],
            [("created_by.$id", 1), ("name_search", 1)],
  

            # Optional (agar user wise filter chahiye)
            "created_by",
            "patient_id",
            "provider_id"
        ]