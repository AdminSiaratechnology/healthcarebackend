from fastapi import APIRouter,Request,HTTPException, Depends
from app.schemas.users import Users
from app.accounts.models.user import UserDoc, UserRole
from app.utils.audit import log_audit
from app.encryption.encryption import encrypt_value,decrypt_value,encrypt_value_deterministic
from app.auth.password import hash_password
from app.auth.deps import get_current_user_id
from app.accounts.models.admin import Admin

from beanie import PydanticObjectId
from app.schemas.admin import (
    AdminProfile,
    PersonalProfile,
    PersonalInformation,
    ContactInformation,
    AddressDetails,
    EmergencyContact,
    ProfessionalProfile,
    ProfessionalCredentials,
    MedicalLicenseInformation,
    BoardCertification,
    Education,
    AdditionalCertification,
    OrganizationProfile,
    OrganizationDetails,
    PrimaryOrganizationContact,
    SecurityProfile,
    TwoFactorAuth,
    SettingsProfile,
    RegionalSettings,
    NotificationPreferences,
    EmailNotificationSchedule,
    DisplayAppearance,
    EmailSignature,
    DangerZone,
)

# router = APIRouter()
router = APIRouter(prefix="/account", tags=["Account"])


def _build_default_admin_profile(users: Users) -> AdminProfile:
    """Constructs the baseline admin profile when payload does not include one."""
    return AdminProfile(
        personal=PersonalProfile(
            personal_information=PersonalInformation(
                photo_url=None,
                first_name=users.full_name,
                middle_name=None,
                last_name="",
                suffix_credential=None,
                date_of_birth=None,
                gender=None,
            ),
            contact_information=ContactInformation(
                primary_email_address=users.email,
                alternate_email=None,
                primary_phone=users.phone,
                alternate_phone=None,
                fax_number=None,
            ),
            address_details=AddressDetails(),
            emergency_contact=EmergencyContact(),
        ),
        professional=ProfessionalProfile(
            professional_credentials=ProfessionalCredentials(),
            medical_license_information=MedicalLicenseInformation(),
            board_certification=BoardCertification(),
            education=Education(),
            additional_certifications=[],
        ),
        organization=OrganizationProfile(
            organization_details=OrganizationDetails(),
            primary_organization_contact=PrimaryOrganizationContact(),
        ),
        security=SecurityProfile(
            two_factor_auth=TwoFactorAuth(authenticator_app_enabled=False),
            session_timeout_minutes=None,
            auto_lock_minutes=None,
            ip_whitelist=[],
            login_notifications_enabled=False,
            api_access_enabled=False,
            security_audit_log_enabled=False,
            compliance_certifications=[],
        ),
        settings=SettingsProfile(
            regional_settings=RegionalSettings(),
            notification_preferences=NotificationPreferences(),
            email_notification_schedule=EmailNotificationSchedule(),
            display_appearance=DisplayAppearance(),
            email_signature=EmailSignature(),
            danger_zone=DangerZone(),
        ),
    )

@router.post("/users")
async def user_registrations(users: Users, request: Request):
    try:
        client_encryption = request.app.client_encryption
        dek_id = request.app.dek_id
        if users.email:
            encrypted_email = encrypt_value_deterministic(client_encryption, dek_id, users.email)
            existing_email_user = await UserDoc.find_one({"email": encrypted_email})
            if existing_email_user:
                raise HTTPException(status_code=400, detail="Email already exists")

        encrypted_doc = {
            'full_name': encrypt_value(client_encryption, dek_id, users.full_name),

            'email': encrypt_value_deterministic(client_encryption, dek_id, users.email)
                      if users.email else None,

            'phone': encrypt_value_deterministic(client_encryption, dek_id, users.phone)
                     if users.phone else None,

            'role': encrypt_value(client_encryption, dek_id, users.role.value),

            'password': encrypt_value(client_encryption, dek_id, hash_password(users.password))
                                if hash_password(users.password) else None
        }

        user = UserDoc(**encrypted_doc)
        await user.insert()

        if users.role == UserRole.ADMIN:
            print("Creating admin profile")
            # build profile object (from payload or defaults)
            profile_obj = users.admin_profile or _build_default_admin_profile(users)
            # convert to JSON-safe dict (dates → strings, enums → values) before encryption
            profile_data = profile_obj.model_dump(mode="json")
            # encrypt full profile as Binary, similar to how UserDoc fields are encrypted
            encrypted_profile = encrypt_value(
                client_encryption,
                dek_id,
                profile_data,
            )
            admin_doc = Admin(user=user, user_id=str(user.id), profile=encrypted_profile)
            await admin_doc.insert()
        # raw = decrypt_value(client_encryption, user.role)
        # role = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        # print("rolessssssss",role)
        

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="CREATE",
            resource="patient",
            resource_id=str(user.id),
            status="success",
            notes="Patient encrypted data inserted"
        )

        return {
            "inserted_id": str(user.id),
            "user": "User saved successfully!",
            "admin_profile_created": users.role == UserRole.ADMIN
        }

    except Exception as e:
        await log_audit(
            request=request,
            user_id="anonymous",
            action="CREATE",
            resource="patient",
            resource_id="N/A",
            status="failed",
            notes=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users")
async def get_users(request: Request):
    client_encryption = request.app.client_encryption

    users = await UserDoc.find().to_list()

    decrypted_users = [u.decrypt_fields(client_encryption) for u in users]

    return {"data": decrypted_users}

