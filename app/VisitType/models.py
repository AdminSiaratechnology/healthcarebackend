from beanie import Document, Link, Indexed
from datetime import datetime, timezone
from typing_extensions import Annotated
from pydantic import ConfigDict, Field
from app.accounts.models.user import UserDoc


class VisitType(Document):

    # 🔗 Relations
    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None

    name: Annotated[str, Indexed()] = Field(..., description="Name of the visit type")

    # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: datetime | None = None

    status: Annotated[str, Indexed()] = "active"

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "VisitType"
        indexes = [
            [("name", 1)],
            [("is_deleted", 1)],
            [("status", 1)],
        ]
       