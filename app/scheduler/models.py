from beanie import Document, Link, Indexed
from bson import Binary
from datetime import datetime, timezone
from pydantic import Field
from typing import Optional
from typing_extensions import Annotated

from app.accounts.models.user import UserDoc


class Scheduler(Document):
    # 🔗 Relations (Admin ownership)
    created_by: Optional[Link[UserDoc]] = Indexed()
    deleted_by: Optional[Link[UserDoc]] = None
    user: Optional[Link[UserDoc]] = None  # doctor/patient

    # 🔐 Encrypted
    first_name: Optional[Binary] = None
    middle_name: Optional[Binary] = None
    last_name: Optional[Binary] = None

    # 🟢 Searchable
    first_name_search: Annotated[str, Indexed()] = ""
    middle_name_search: Annotated[str, Indexed()] = ""
    last_name_search: Annotated[str, Indexed()] = ""

    # 🔁 Soft delete
    is_deleted: Annotated[bool, Indexed()] = False
    deleted_at: Optional[datetime] = None
    status: Annotated[str, Indexed()] = "active"

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "arbitrary_types_allowed": True
    }

    class Settings:
        name = "schedulers"

        indexes = [
            # 🔥 KEY INDEX (multi-tenant isolation)
            [("created_by.$id", 1), ("is_deleted", 1)],

            # optional sorting
            [("created_at", -1)]
        ]