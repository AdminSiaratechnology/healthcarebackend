from enum import Enum
from typing import Optional, List
from datetime import date
from pydantic import BaseModel, Field, EmailStr


class Gender(str, Enum):
    male = "male"
    female = "female"
    other = "other"


class Theme(str, Enum):
    light = "light"
    dark = "dark"
    auto_system = "auto_system"


class DashboardLayout(str, Enum):
    compact = "compact"
    comfortable = "comfortable"
    spacious = "spacious"


class EmailSchedule(str, Enum):
    real_time = "real_time"
    hourly_digest = "hourly_digest"
    daily_digest = "daily_digest"
    weekly_digest = "weekly_digest"


class PersonalInformation(BaseModel):
    photo_url: Optional[str] = None
    first_name: str
    middle_name: Optional[str] = None
    last_name: str
    suffix_credential: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[Gender] = None


class ContactInformation(BaseModel):
    primary_email_address: Optional[EmailStr] = None
    alternate_email: Optional[EmailStr] = None
    primary_phone: Optional[str] = None
    alternate_phone: Optional[str] = None
    fax_number: Optional[str] = None


class AddressDetails(BaseModel):
    street_address: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    country: Optional[str] = None


class EmergencyContact(BaseModel):
    emergency_contact_name: Optional[str] = None
    relationship: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_email: Optional[EmailStr] = None


class PersonalProfile(BaseModel):
    personal_information: PersonalInformation
    contact_information: ContactInformation
    address_details: AddressDetails
    emergency_contact: EmergencyContact


class ProfessionalCredentials(BaseModel):
    professional_title: Optional[str] = None
    department_division: Optional[str] = None
    specialization: Optional[str] = None
    years_of_experience: Optional[int] = Field(default=None, ge=0)


class MedicalLicenseInformation(BaseModel):
    medical_license_number: Optional[str] = None
    license_state: Optional[str] = None
    license_expiration_date: Optional[date] = None
    npi_number: Optional[str] = None
    dea_number: Optional[str] = None


class BoardCertification(BaseModel):
    board_certification: Optional[str] = None
    certification_expiration: Optional[date] = None


class Education(BaseModel):
    medical_school: Optional[str] = None
    graduation_year: Optional[int] = Field(default=None, ge=1900, le=2100)


class AdditionalCertification(BaseModel):
    name: str
    attachment_url: Optional[str] = None


class ProfessionalProfile(BaseModel):
    professional_credentials: ProfessionalCredentials
    medical_license_information: MedicalLicenseInformation
    board_certification: BoardCertification
    education: Education
    additional_certifications: List[AdditionalCertification] = []


class OrganizationDetails(BaseModel):
    organization_name: Optional[str] = None
    organization_id: Optional[str] = None
    tax_id_ein: Optional[str] = None
    organization_type: Optional[str] = None


class PrimaryOrganizationContact(BaseModel):
    contact_person_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None


class OrganizationProfile(BaseModel):
    organization_details: OrganizationDetails
    primary_organization_contact: PrimaryOrganizationContact


class TwoFactorAuth(BaseModel):
    authenticator_app_enabled: bool = False


class SecurityProfile(BaseModel):
    two_factor_auth: TwoFactorAuth
    session_timeout_minutes: Optional[int] = None
    auto_lock_minutes: Optional[int] = None
    ip_whitelist: List[str] = []
    login_notifications_enabled: bool = False
    api_access_enabled: bool = False
    security_audit_log_enabled: bool = False
    compliance_certifications: List[str] = []


class RegionalSettings(BaseModel):
    timezone: Optional[str] = None
    language: Optional[str] = None
    date_format: Optional[str] = None
    time_format: Optional[str] = None


class NotificationPreferences(BaseModel):
    email_notifications: bool = False
    sms_notifications: bool = False
    system_alerts: bool = False
    maintenance_notifications: bool = False
    billing_notifications: bool = False


class EmailNotificationSchedule(BaseModel):
    schedule: EmailSchedule = EmailSchedule.real_time


class DisplayAppearance(BaseModel):
    theme: Theme = Theme.auto_system
    dashboard_layout: DashboardLayout = DashboardLayout.comfortable
    show_navigation_labels: bool = True
    compact_tables: bool = False


class EmailSignature(BaseModel):
    signature: Optional[str] = None


class DangerZone(BaseModel):
    deactivate_account: bool = False
    delete_account: bool = False


class SettingsProfile(BaseModel):
    regional_settings: RegionalSettings
    notification_preferences: NotificationPreferences
    email_notification_schedule: EmailNotificationSchedule
    display_appearance: DisplayAppearance
    email_signature: EmailSignature
    danger_zone: DangerZone


class AdminProfile(BaseModel):
    personal: PersonalProfile
    professional: ProfessionalProfile
    organization: OrganizationProfile
    security: SecurityProfile
    settings: SettingsProfile

