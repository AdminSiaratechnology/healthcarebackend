from enum import Enum
from beanie import Document, Indexed, Link
from bson import Binary
from datetime import datetime, timezone
from typing import Annotated
from pydantic import Field, ConfigDict
from app.accounts.models.user import UserDoc


class FacilityStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Facility(Document):
    # encrypted full payload
    basic: Binary | None = None

    # deterministic encrypted (queryable)
    facility_name: Annotated[Binary | None, Indexed()] = None

    # plaintext enum (fast filter)
    status: Annotated[FacilityStatus, Indexed()] = FacilityStatus.ACTIVE

    created_by: Link[UserDoc] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facilities"
        indexes = [
            [("facility_name", 1), ("created_by.$id", 1)],
            [("status", 1), ("created_by.$id", 1)],
        ]
