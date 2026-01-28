from beanie import Document, Link, Indexed
from enum import Enum
from datetime import datetime
from typing_extensions import Annotated
from app.accounts.models.user import UserDoc
from app.facility.models.facility import Facility
from pydantic import ConfigDict, Field
from datetime import datetime, timezone

class FacilityRole(str, Enum):
    ADMINISTRATION = "administration"
    DON = "director_of_nursing"
    MANAGER = "manager"
    MEDICAL_DIRECTOR = "medical_director"
    ADMISSIONS_COORDINATOR = "admissions_coordinator"
    IT_ADMINISTRATOR = "it_administrator"
    CHARGE_NURSE = "charge_nurse"

class UserFacilityRole(Document):
    user_id: Link[UserDoc]
    facility_id: Link[Facility]
    role: FacilityRole

    is_primary: bool = False
   

    created_by: Link[UserDoc] | None = None
    deleted_by: Link[UserDoc] | None = None

    is_deleted: Annotated[bool, Indexed()] = False
    status: Annotated[str, Indexed()] = "active"
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "user_facility_roles"
        indexes = [
            [("facility_id.$id", 1), ("is_deleted", 1)],
        ]
