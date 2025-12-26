from beanie import Document, Link
from pydantic import Field,ConfigDict
from datetime import datetime, timezone
from typing import Optional
from app.accounts.models.user import UserDoc
from bson import Binary

class DeviceDoc(Document):
    created_by: Link[UserDoc]

    device_name: Binary                 # iPhone 15 Pro
    device_type: Binary                 # mobile / tablet / laptop
    platform: Binary                    # iOS / Android / macOS
    os_version: Binary                  # iOS 17.1
    app_version: Binary                 # App v2.1.3

    battery_percentage: Binary | None = None  # 87
    location: Binary | None = None            # Sunrise Manor

    is_current_device: Binary | None = None
    status:  Binary | None = None   # active | inactive | blocked

    last_active_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "devices"
