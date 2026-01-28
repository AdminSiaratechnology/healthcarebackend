from beanie import Document
from bson import Binary
from datetime import datetime, timezone
from typing import Optional
from enum import Enum
from pydantic import Field
from app.encryption.decrypt_mixin import AutoDecryptMixin
from app.encryption.encrypt_mixin import AutoEncryptMixin

class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    PARTNER = "partner"
    SUB_PARTNER = "sub_partner"
    PHYSICIAN = "physician"
    NURSE_PRACTITIONER = "nurse_practitioner"
    MEDICAL_ASSISTANT = "medical_assistant"
    FACILITY_STAFF = "facility_staff"
    FAMILY = "family"
    DEVELOPER = "developer"
    SUPPORT = "support"
    PROVIDER = "provider"
    PATIENT = "patient"
    SCHEDULER = "scheduler"
    DIRECTOR_OF_NURSING = "director_of_nursing"  # DON


class UserDoc(Document, AutoDecryptMixin, AutoEncryptMixin):
    full_name: Binary
    email: Optional[Binary] = None
    phone: Optional[Binary] = None
    role: Optional[Binary] = None
    is_active: bool = True
    password: Optional[Binary] = None

     # 🔍 Searchable (PLAIN TEXT)
    full_name_search: Optional[str] = None
    email_search: Optional[str] = None
    phone_search: Optional[str] = None


    mpin: Optional[Binary] = None
    mpin_index: Optional[Binary] = None
    qr_code : Optional[Binary] = None
    is_mpin: bool = False
    device_id: Optional[Binary] = None
    google_auth_secret: Optional[Binary] = None
    is_google_auth_enabled: bool = False
    google_auth_verified_at: Optional[datetime] = None
    
    # mfa_verified = bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "arbitrary_types_allowed": True
    }


    class Settings:
        name = "users"
        indexes = [
            [("full_name_search", 1)],
            [("email_search", 1)],
            [("phone_search", 1)],
        ]

    