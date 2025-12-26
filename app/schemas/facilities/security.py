from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum 


class UserRolesAccess(BaseModel):
    is_admin: bool = False
    is_donor: bool = False
    is_charge_nurse: bool = False
    is_provider: bool = False
    is_billing: bool = False
    is_front_desk: bool = False
    


class AuthenticationSessions(BaseModel):
    session_timeout_minutes: Optional[int] = None
    auto_lock_minutes: Optional[int] = None
    


class phiExportSettings(BaseModel):
    allow_usb_export: bool = False
    allow_email_export: bool = False
    secure_fax_only: bool = False
    

class BreakGlassAudit(BaseModel):
    break_glass_policy : Optional[str] = None  # Long text
    autit_retention_years: Optional[int] = None

class PrivacyOfficerInfo(BaseModel):
    officer_name: Optional[str] = None
    email: Optional[str] = None
    contact_number: Optional[str] = None

 


class SecuritySchema(BaseModel):
    user_roles_access: Optional[UserRolesAccess] = None
    authentication_sessions: Optional[AuthenticationSessions] = None
    phi_export_settings: Optional[phiExportSettings] = None
    break_glass_audit: Optional[BreakGlassAudit] = None
    privacy_officer_info: Optional[PrivacyOfficerInfo] = None
    # breach_contacts: List[BreachContacts] = Field(default_factory=list)