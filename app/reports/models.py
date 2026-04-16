from beanie import Document, Link, Indexed
from datetime import datetime, timezone
from typing import Dict, Any
from typing_extensions import Annotated

from app.patients.models.patients import PatientDoc
from app.clinicalmonitoring.models.template_builder import TemplateBuilderDoc
from app.accounts.models.user import UserDoc


class PatientReportDoc(Document):

    # 🔗 Relations
    patient_id: Link[PatientDoc]
    template_id: Link[TemplateBuilderDoc]

    created_by: Link[UserDoc] | None = None

    # 🔥 MAIN DATA (LLM output)
    data: Dict[str, Any]

    # 🟢 Status
    status: Annotated[str, Indexed()] = "active"

    # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: datetime | None = None

    # 🕒 timestamps
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)

    class Settings:
        name = "patient_reports"
        indexes = [
            [("patient_id.$id", 1), ("template_id.$id", 1)],
            "status",
            "is_deleted"
        ]