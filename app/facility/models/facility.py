from enum import Enum
from beanie import Document, Indexed, Link
from bson import Binary
from datetime import datetime, timezone
from typing import Annotated
from pydantic import Field, ConfigDict
from app.accounts.models.user import UserDoc
from app.schemas.facility import FacilityStatus



class Facility(Document):
    # encrypted full payload
    basic: Binary | None = None

    # 🟢 searchable plain text
    facility_name_search: Annotated[str, Indexed()]
    
    # plaintext enum (fast filter)
    status: Annotated[str, Indexed()] = "active"

    
     # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facilities"
        indexes = [
            [("facility_name_search", 1), ("created_by.$id", 1)],
            [("status", 1), ("created_by.$id", 1)],
            [("is_deleted", 1), ("facility_id.$id", 1)],
        ]
