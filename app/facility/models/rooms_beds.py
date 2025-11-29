from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone
from pydantic import Field, ConfigDict
from app.facility.models.facility import Facility


class RoomsBedsDoc(Document):
    facility: Link[Facility]
    data: Binary | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "facility_rooms_beds"

