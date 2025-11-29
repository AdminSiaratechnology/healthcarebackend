from enum import Enum
from beanie import Document, Link
from typing import Optional
from pydantic import EmailStr, Field
from datetime import datetime, timezone

class PartnerType(str, Enum):
    PARTNER = "partner"
    SUB_PARTNER = "sub_partner"


class Partner(Document):
    name: str
    type: PartnerType
    parent_partner: Optional[Link["Partner"]] = None

    contact_person: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

    commission_percent: Optional[float] = None

    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "partners"
