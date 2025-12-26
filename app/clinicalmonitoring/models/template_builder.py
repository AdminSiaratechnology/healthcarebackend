from beanie import Document, Link
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

class TemplateBuilderDoc(Document, AutoEncryptMixin, AutoDecryptMixin):
    sub_category_id: Link[SubcategoryDoc]
    patient_id : Link[PatientDoc] | None = None
    provider_id : Link[Provider] | None = None
    template_name : Binary
    short_name : Binary | None = None
    discipline : Binary | None = None
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "template_builder"