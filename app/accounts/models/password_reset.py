from beanie import Document, Link
from datetime import datetime, timezone, timedelta
from pydantic import Field
from app.accounts.models.user import UserDoc


class PasswordReset(Document):
    user: Link[UserDoc]
    user_id: str
    email: str
    otp_hash: str
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=10))
    verified: bool = False
    used: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "password_resets"
