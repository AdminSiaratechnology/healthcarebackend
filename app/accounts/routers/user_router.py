from fastapi import APIRouter,Request,HTTPException, Depends
from app.schemas.users import Users, AdminUpdateSchema
from app.accounts.models.user import UserDoc, UserRole
from app.utils.audit import log_audit
from app.encryption.encryption import encrypt_value,decrypt_value,encrypt_value_deterministic, init_encryption
from app.auth.password import hash_password
from app.auth.deps import get_current_user_id
from app.accounts.models.admin import Admin
from datetime import datetime, timezone

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

# @router.post("/users")
# async def user_registrations(users: Users, request: Request):
#     try:
#         client_encryption = request.app.client_encryption
#         dek_id = request.app.dek_id
#         if users.email:
#             encrypted_email = encrypt_value_deterministic(client_encryption, dek_id, users.email)
#             existing_email_user = await UserDoc.find_one({"email": encrypted_email})
#             if existing_email_user:
#                 raise HTTPException(status_code=400, detail="Email already exists")
#         hashed_password = hash_password(users.password)

#         encrypted_doc = {
#             'full_name': encrypt_value(client_encryption, dek_id, users.full_name),

#             'email': encrypt_value_deterministic(client_encryption, dek_id, users.email)
#                       if users.email else None,

#             'phone': encrypt_value_deterministic(client_encryption, dek_id, users.phone)
#                      if users.phone else None,

#             'role': encrypt_value(client_encryption, dek_id, users.role.value),

#             'password': encrypt_value(client_encryption, dek_id, hashed_password)
#                 if hashed_password else None
#         }

#         user = UserDoc(**encrypted_doc)
#         await user.insert()

#         if users.role == UserRole.ADMIN:
#             print("Creating admin profile")
#             # build profile object (from payload or defaults)
#             profile_obj = users.admin_profile or _build_default_admin_profile(users)
#             # convert to JSON-safe dict (dates → strings, enums → values) before encryption
#             profile_data = profile_obj.model_dump(mode="json")
#             # encrypt full profile as Binary, similar to how UserDoc fields are encrypted
#             encrypted_profile = encrypt_value(
#                 client_encryption,
#                 dek_id,
#                 profile_data,
#             )
#             admin_doc = Admin(user=user, user_id=str(user.id), profile=encrypted_profile)
#             await admin_doc.insert()
        

#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="CREATE",
#             resource="patient",
#             resource_id=str(user.id),
#             status="success",
#             notes="Patient encrypted data inserted"
#         )

#         return {
#             "inserted_id": str(user.id),
#             "user": "User saved successfully!",
#             "admin_profile_created": users.role == UserRole.ADMIN
#         }

#     except Exception as e:
#         await log_audit(
#             request=request,
#             user_id="anonymous",
#             action="CREATE",
#             resource="patient",
#             resource_id="N/A",
#             status="failed",
#             notes=str(e)
#         )
#         raise HTTPException(status_code=500, detail=str(e))


import json
import traceback


@router.post("/users")
async def user_registrations(users: Users, request: Request):
    try:
        client_encryption = request.app.client_encryption
        dek_id = request.app.dek_id

        print("🚀 API HIT")

        # 🔹 Check existing email (deterministic encryption)
        if users.email is not None:
            encrypted_email = encrypt_value_deterministic(
                client_encryption, dek_id, users.email
            )

            existing_email_user = await UserDoc.find_one({"email": encrypted_email})

            if existing_email_user:
                raise HTTPException(
                    status_code=400,
                    detail="Email already exists"
                )

        # 🔹 Hash password ONLY ONCE
        hashed_password = hash_password(users.password)

        # 🔹 Build encrypted user document
        encrypted_doc = {
            "full_name": encrypt_value(client_encryption, dek_id, users.full_name),

            "email": encrypt_value_deterministic(client_encryption, dek_id, users.email)
            if users.email else None,

            "phone": encrypt_value_deterministic(client_encryption, dek_id, users.phone)
            if users.phone else None,

            "role": encrypt_value(client_encryption, dek_id, users.role.value),

            # 🔐 Hash + Encrypt password
            "password": encrypt_value(client_encryption, dek_id, hashed_password)
            if hashed_password else None,

            # 🔍 Searchable (PLAIN TEXT)
            "full_name_search": users.full_name.lower().strip(),
            "email_search": users.email.lower().strip() if users.email else None,
            "phone_search": users.phone.strip() if users.phone else None,
        }

        # 🔹 Save user
        user = UserDoc(**encrypted_doc)
        await user.insert()

        # 🔹 Admin profile handling
        if users.role == UserRole.ADMIN:
            print("👤 Creating admin profile")

            profile_obj = users.admin_profile or _build_default_admin_profile(users)

            # convert to JSON-safe dict
            profile_data = profile_obj.model_dump(mode="json")

            # ❗ dict → string
            profile_data_str = json.dumps(profile_data)

            encrypted_profile = encrypt_value(
                client_encryption,
                dek_id,
                profile_data_str,
            )

            admin_doc = Admin(
                user=user,
                user_id=str(user.id),
                profile=encrypted_profile,
            )

            await admin_doc.insert()

        # 🔹 Audit log
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="CREATE",
            resource="patient",
            resource_id=str(user.id),
            status="success",
            notes="Patient encrypted data inserted",
        )

        return {
            "inserted_id": str(user.id),
            "message": "User saved successfully!",
            "admin_profile_created": users.role == UserRole.ADMIN,
        }

    # ✅ IMPORTANT: preserve HTTPException (400, 401, etc.)
    except HTTPException as e:
        raise e

    # ❌ Only real errors come here
    except Exception as e:
        print("❌ ERROR TRACE:", traceback.format_exc())

        await log_audit(
            request=request,
            user_id="anonymous",
            action="CREATE",
            resource="patient",
            resource_id="N/A",
            status="failed",
            notes=str(e),
        )

        raise HTTPException(
            status_code=500,
            detail="Internal Server Error"
        )

@router.get("/users")
async def get_users(request: Request):
    client_encryption = request.app.client_encryption

    users = await UserDoc.find().to_list()

    decrypted_users = [u.decrypt_fields(client_encryption) for u in users]

    return {"data": decrypted_users}


@router.get("/getall-admin")
async def get_all_admins(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        current_user = await UserDoc.get(current_user_id)
        if not current_user:
            raise HTTPException(status_code=404, detail="User not found")

        current_role = decrypt_value(ce, current_user.role) if current_user.role else None
        if current_role != UserRole.SUPER_ADMIN.value:
            raise HTTPException(
                status_code=403,
                detail="Only super_admin can access admin details",
            )

        admin_docs = await Admin.find().sort("-created_at").to_list()

        result = []
        for admin_doc in admin_docs:
            linked_user = None
            if admin_doc.user_id:
                try:
                    linked_user = await UserDoc.get(PydanticObjectId(admin_doc.user_id))
                except Exception:
                    linked_user = None

            result.append(
                {
                    "admin_id": str(admin_doc.id),
                    "user_id": str(linked_user.id) if linked_user else str(admin_doc.user_id),
                    "full_name": decrypt_value(ce, linked_user.full_name) if linked_user and linked_user.full_name else None,
                    "email": decrypt_value(ce, linked_user.email) if linked_user and linked_user.email else None,
                    "phone": decrypt_value(ce, linked_user.phone) if linked_user and linked_user.phone else None,
                    "role": decrypt_value(ce, linked_user.role) if linked_user and linked_user.role else None,
                    "is_active": linked_user.is_active if linked_user else None,
                }
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/update-admin/{admin_id}")
async def update_admin_by_super_admin(
    admin_id: str,
    payload: AdminUpdateSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            raise HTTPException(status_code=500, detail="Encryption key is not initialized")

        current_user = await UserDoc.get(current_user_id)
        if not current_user:
            raise HTTPException(status_code=404, detail="User not found")

        current_role = decrypt_value(ce, current_user.role) if current_user.role else None
        if current_role != UserRole.SUPER_ADMIN.value:
            raise HTTPException(
                status_code=403,
                detail="Only super_admin can update admin details",
            )

        try:
            admin_obj_id = PydanticObjectId(admin_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid admin_id")

        admin_doc = await Admin.get(admin_obj_id)
        if not admin_doc:
            raise HTTPException(status_code=404, detail="Admin record not found")

        if not admin_doc.user_id:
            raise HTTPException(status_code=404, detail="Linked user not found")

        try:
            linked_user = await UserDoc.get(PydanticObjectId(admin_doc.user_id))
        except Exception:
            linked_user = None

        if not linked_user:
            raise HTTPException(status_code=404, detail="Linked user not found")

        if payload.email is not None:
            encrypted_email = encrypt_value_deterministic(ce, dek_id, payload.email)
            existing_email_user = await UserDoc.find_one({"email": encrypted_email})
            if existing_email_user and str(existing_email_user.id) != str(linked_user.id):
                raise HTTPException(status_code=400, detail="Email already exists")
            linked_user.email = encrypted_email
            linked_user.email_search = payload.email.lower().strip()

        if payload.phone is not None:
            linked_user.phone = encrypt_value_deterministic(ce, dek_id, payload.phone)
            linked_user.phone_search = payload.phone.strip()

        if payload.full_name is not None:
            linked_user.full_name = encrypt_value(ce, dek_id, payload.full_name)
            linked_user.full_name_search = payload.full_name.lower().strip()

        

        if payload.is_active is not None:
            linked_user.is_active = payload.is_active

        linked_user.updated_at = datetime.now(timezone.utc)
        await linked_user.save()

        

        return {
            "success": True,
            "admin_id": str(admin_doc.id),
            "user_id": str(linked_user.id),
            "message": "Admin updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

