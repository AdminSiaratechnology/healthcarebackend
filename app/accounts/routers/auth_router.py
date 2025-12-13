from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Optional, Tuple
import base64
import io
import pyotp
import qrcode
import os
import uuid
import json
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    ProfileResponse,
    MPINSetRequest,
    MPINLoginRequest,
    MPINOnlyLoginRequest,
    GoogleAuthSetupRequest,
    GoogleAuthSetupResponse,
    GoogleAuthVerifyRequest,
    ChangePasswordRequest,
    ForgotMPINSetRequest,
    ForgotPasswordRequest,
    ForgotPasswordVerifyRequest,
    ForgotPasswordResetRequest,
    EditProfileRequest,
)
from app.schemas.admin import AdminProfile
from app.accounts.models.user import UserDoc
from app.accounts.models.admin import Admin
from app.provider.models.providers import Provider
from app.schemas.provider.basic import BasicInfo
from app.auth.password import verify_password, hash_password
from app.utils.audit import log_audit
from app.encryption.encryption import encrypt_value_deterministic, decrypt_value, encrypt_value
from app.database.config import settings
from app.utils.email import send_email
from app.accounts.models.password_reset import PasswordReset
from app.utils.s3_utils import get_bucket_name, s3_client, safe_filename, put_object, presign


# router = APIRouter()
router = APIRouter(prefix="/account", tags=["Account"])

UPLOAD_DIR_PROFILE_PHOTOS = "./uploads/profile_photos"
os.makedirs(UPLOAD_DIR_PROFILE_PHOTOS, exist_ok=True)


def _get_jwt_settings():
    secret = getattr(settings, "JWT_SECRET", None)
    alg = getattr(settings, "JWT_ALGORITHM", "HS256")
    ttl_min = getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60)
    if not secret:
        import os
        import secrets
        env_secret = os.environ.get("JWT_SECRET")
        secret = env_secret or secrets.token_urlsafe(32)
        settings.JWT_SECRET = secret
    return secret, alg, ttl_min


def _decrypt_to_str(client_encryption, value):
    if not value:
        return None
    val = decrypt_value(client_encryption, value)
    return val.decode("utf-8") if isinstance(val, bytes) else val


async def _get_user_from_authorization(request: Request) -> Tuple[UserDoc, Optional[str]]:
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = auth.split(" ", 1)[1]
    secret, alg, _ = _get_jwt_settings()
    try:
        decoded = jwt.decode(token, secret, algorithms=[alg])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    jti = decoded.get("jti")
    revoked = getattr(request.app, "revoked_jti", set())
    if jti in revoked:
        raise HTTPException(status_code=401, detail="Token revoked")

    user_id = decoded.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token subject")

    user = await UserDoc.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    client_encryption = request.app.client_encryption
    email_val = _decrypt_to_str(client_encryption, user.email)
    return user, email_val


async def _get_user_by_email(email: str, request: Request) -> UserDoc:
    client_encryption = request.app.client_encryption
    dek_id = request.app.dek_id
    enc_email = encrypt_value_deterministic(client_encryption, dek_id, email)
    user = await UserDoc.find_one({"email": enc_email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user


async def _find_user_by_google_otp(otp: str, request: Request) -> Tuple[UserDoc, Optional[str]]:
    client_encryption = request.app.client_encryption
    users = await UserDoc.find({"google_auth_secret": {"$ne": None}}).to_list()
    matches = []
    for u in users:
        secret = _decrypt_to_str(client_encryption, u.google_auth_secret)
        if not secret:
            continue
        totp = pyotp.TOTP(secret)
        if totp.verify(otp, valid_window=1):
            matches.append(u)
    if not matches:
        raise HTTPException(status_code=401, detail="Invalid OTP")
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail="Multiple users match OTP")
    user = matches[0]
    email_val = _decrypt_to_str(client_encryption, user.email)
    return user, email_val


async def _authenticate_user(email: str, password: str, request: Request) -> UserDoc:
    user = await _get_user_by_email(email, request)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User inactive")
    client_encryption = request.app.client_encryption
    hashed = _decrypt_to_str(client_encryption, user.password)
    if not hashed or not verify_password(password, hashed):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user


def _generate_token_for_user(user: UserDoc, email_value: Optional[str], request: Request) -> str:
    secret, alg, ttl_min = _get_jwt_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=ttl_min)
    jti = str(uuid4())

    client_encryption = request.app.client_encryption
    role_val = _decrypt_to_str(client_encryption, user.role)

    claims = {
        "sub": str(user.id),
        "email": email_value,
        "role": role_val,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
    }

    return jwt.encode(claims, secret, algorithm=alg)


def _build_qr_code_image(data: str) -> str:
    qr = qrcode.QRCode(border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _build_default_admin_profile_for_user(user: UserDoc, client_encryption) -> AdminProfile:
    """Construct a baseline admin profile from an existing user."""
    full_name = _decrypt_to_str(client_encryption, user.full_name)
    email = _decrypt_to_str(client_encryption, user.email)
    phone = _decrypt_to_str(client_encryption, user.phone)

    data = {
        "personal": {
            "personal_information": {
                "photo_url": None,
                "first_name": full_name,
                "middle_name": None,
                "last_name": "",
                "suffix_credential": None,
                "date_of_birth": None,
                "gender": None,
            },
            "contact_information": {
                "primary_email_address": email,
                "alternate_email": None,
                "primary_phone": phone,
                "alternate_phone": None,
                "fax_number": None,
            },
            "address_details": {},
            "emergency_contact": {},
        },
        "professional": {
            "professional_credentials": {},
            "medical_license_information": {},
            "board_certification": {},
            "education": {},
            "additional_certifications": [],
        },
        "organization": {
            "organization_details": {},
            "primary_organization_contact": {},
        },
        "security": {
            "two_factor_auth": {"authenticator_app_enabled": False},
            "session_timeout_minutes": None,
            "auto_lock_minutes": None,
            "ip_whitelist": [],
            "login_notifications_enabled": False,
            "api_access_enabled": False,
            "security_audit_log_enabled": False,
            "compliance_certifications": [],
        },
        "settings": {
            "regional_settings": {},
            "notification_preferences": {},
            "email_notification_schedule": {},
            "display_appearance": {},
            "email_signature": {},
            "danger_zone": {},
        },
    }

    return AdminProfile.model_validate(data)


@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request):
    user = await _authenticate_user(payload.email, payload.password, request)
    token = _generate_token_for_user(user, payload.email, request)

    await log_audit(
        request=request,
        user_id = str(user.id),
        action="LOGIN",
        resource="auth",
        resource_id=str(user.id),
        status="success",
        notes="User logged in"
    )

    return TokenResponse(access_token=token, token_type="bearer")


# @router.post("/auth/google-auth/setup", response_model=GoogleAuthSetupResponse)
# async def setup_google_auth(payload: GoogleAuthSetupRequest, request: Request):
#     user = await _authenticate_user(payload.email, payload.password, request)
#     client_encryption = request.app.client_encryption
#     dek_id = request.app.dek_id

#     previously_enabled = user.is_google_auth_enabled
#     secret = pyotp.random_base32()
#     totp = pyotp.TOTP(secret)
#     issuer = "Healthcare Management System"
#     provisioning_uri = totp.provisioning_uri(name=payload.email, issuer_name=issuer)
#     qr_image = _build_qr_code_image(provisioning_uri)

#     user.google_auth_secret = encrypt_value(client_encryption, dek_id, secret)
    
#     user.is_google_auth_enabled = False
#     user.google_auth_verified_at = None
#     await user.save()

#     await log_audit(
#         request=request,
#         action="GOOGLE_AUTH_SETUP",
#         resource="auth",
#         resource_id=str(user.id),
#         status="success",
#         notes="Generated Google Authenticator secret"
#     )

#     return GoogleAuthSetupResponse(
#         secret=secret,
#         qr_code_png=qr_image,
#         is_already_enabled=previously_enabled
#     )


@router.post("/auth/google-auth/setup", response_model=GoogleAuthSetupResponse)
async def setup_google_auth(payload: GoogleAuthSetupRequest, request: Request):
    user = await _authenticate_user(payload.email, payload.password, request)
    client_encryption = request.app.client_encryption
    dek_id = request.app.dek_id

    # Agar already enabled hai → naya secret/QR mat banao
    if user.is_google_auth_enabled:
        return GoogleAuthSetupResponse(
            secret=None,
            qr_code_png=None,
            is_already_enabled=True
        )

    # Yaha sirf tab aayega jab enabled == False ho
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    issuer = "Healthcare Management System"
    provisioning_uri = totp.provisioning_uri(name=payload.email, issuer_name=issuer)

    qr_image = _build_qr_code_image(provisioning_uri)

    user.google_auth_secret = encrypt_value(client_encryption, dek_id, secret)
    user.is_google_auth_enabled = False
    user.google_auth_verified_at = None
    await user.save()

    return GoogleAuthSetupResponse(
        secret=secret,
        qr_code_png=qr_image,
        is_already_enabled=False
    )


@router.post("/auth/google-auth/verify", response_model=TokenResponse)
async def verify_google_auth(payload: GoogleAuthVerifyRequest, request: Request):
    try:
        user, email_value = await _get_user_from_authorization(request)
    except HTTPException as e:
        if e.status_code == 401:
            user, email_value = await _find_user_by_google_otp(payload.otp, request)
        else:
            raise

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User inactive")
    client_encryption = request.app.client_encryption

    secret = _decrypt_to_str(client_encryption, user.google_auth_secret)
    if not secret:
        raise HTTPException(status_code=400, detail="Google Authenticator not configured")

    totp = pyotp.TOTP(secret)
    if not totp.verify(payload.otp, valid_window=1):
        raise HTTPException(status_code=401, detail="Invalid OTP")

    user.is_google_auth_enabled = True
    user.google_auth_verified_at = datetime.now(timezone.utc)
    await user.save()

    token = _generate_token_for_user(user, email_value, request)

    await log_audit(
        request=request,
        user_id=str(user.id),
        action="GOOGLE_AUTH_VERIFY",
        resource="auth",
        resource_id=str(user.id),
        status="success",
        notes="Google Authenticator verified and login granted"
    )

    return TokenResponse(access_token=token, token_type="bearer")


@router.post("/auth/logout")
async def logout(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=400, detail="Missing bearer token")

    token = auth.split(" ", 1)[1]
    secret, alg, _ = _get_jwt_settings()
    try:
        payload = jwt.decode(token, secret, algorithms=[alg])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    jti = payload.get("jti")
    sub = payload.get("sub")
    if not jti:
        raise HTTPException(status_code=400, detail="Token missing jti")

    revoked = getattr(request.app, "revoked_jti", None)
    if revoked is None:
        request.app.revoked_jti = set()
        revoked = request.app.revoked_jti
    revoked.add(jti)

    await log_audit(
        request=request,
        user_id= sub or "anonymous",
        action="LOGOUT",
        resource="auth",
        resource_id=sub or "N/A",
        status="success",
        notes="User logged out"
    )

    return {"message": "Logged out"}


@router.get("/auth/profile", response_model=ProfileResponse)
async def get_profile(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = auth.split(" ", 1)[1]
    secret, alg, _ = _get_jwt_settings()
    try:
        payload = jwt.decode(token, secret, algorithms=[alg])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    jti = payload.get("jti")
    revoked = getattr(request.app, "revoked_jti", set())
    if jti in revoked:
        raise HTTPException(status_code=401, detail="Token revoked")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token subject")

    client_encryption = request.app.client_encryption
    user = await UserDoc.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    def _dec(v):
        if not v:
            return None
        val = decrypt_value(client_encryption, v)
        return val.decode("utf-8") if isinstance(val, bytes) else val

    full_name = _dec(user.full_name)
    email = _dec(user.email)
    phone = _dec(user.phone)
    role_val = _dec(user.role)

    admin_profile = None
    provider_profile = None
    provider_profile_pic_base64 = None
    if role_val == "admin":
        admin_doc = await Admin.find_one(Admin.user_id == str(user.id))
        if admin_doc:
            dec_admin = admin_doc.decrypt_fields(client_encryption)
            admin_profile = dec_admin.get("profile")
    elif role_val == "provider":
        provider_doc = await Provider.find_one(Provider.user_id == str(user.id))
        if provider_doc:
            dec_provider = provider_doc.decrypt_fields(client_encryption)
            raw_profile = dec_provider.get("profile")
            profile_dict = {}
            if isinstance(raw_profile, (bytes, bytearray)):
                try:
                    profile_dict = json.loads(raw_profile.decode("utf-8"))
                except Exception:
                    profile_dict = {}
            elif isinstance(raw_profile, str):
                try:
                    profile_dict = json.loads(raw_profile)
                except Exception:
                    profile_dict = {}
            elif isinstance(raw_profile, dict):
                profile_dict = raw_profile
            try:
                provider_profile = BasicInfo.model_validate(profile_dict)
            except Exception:
                provider_profile = None

            raw_pic = dec_provider.get("profile_pic")
            if isinstance(raw_pic, (bytes, bytearray)):
                try:
                    provider_profile_pic_base64 = base64.b64encode(raw_pic).decode("utf-8")
                except Exception:
                    provider_profile_pic_base64 = None

    return ProfileResponse(
        id=str(user.id),
        full_name=full_name,
        email=email,
        phone=phone,
        role=role_val,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        admin_profile=admin_profile,
        provider_profile=provider_profile,
        provider_profile_pic_base64=provider_profile_pic_base64,
    )


@router.put("/auth/profile", response_model=ProfileResponse)
async def update_profile(payload: EditProfileRequest, request: Request):
    # Reuse common auth helper
    user, _ = await _get_user_from_authorization(request)

    client_encryption = request.app.client_encryption
    dek_id = request.app.dek_id

    # Update basic user fields if provided
    if payload.full_name is not None:
        user.full_name = encrypt_value(client_encryption, dek_id, payload.full_name)
    if payload.phone is not None:
        user.phone = encrypt_value(client_encryption, dek_id, payload.phone)

    user.updated_at = datetime.now(timezone.utc)
    await user.save()

    # Determine role for response and possible admin profile update
    role_val = _decrypt_to_str(client_encryption, user.role)

    admin_profile = None
    if role_val == "admin":
        # Load or create admin document
        admin_doc = await Admin.find_one(Admin.user_id == str(user.id))

        if payload.admin_profile is not None:
            if not admin_doc:
                admin_doc = Admin(user=user, user_id=str(user.id))

            # Set plain profile data before encryption
            admin_doc.profile = payload.admin_profile.model_dump(mode="json", serialize_as_any=True)

            # Encrypt configured fields and assign back to the document
            enc_fields = admin_doc.encrypt_fields(client_encryption, dek_id)
            for field_name, value in enc_fields.items():
                setattr(admin_doc, field_name, value)

            admin_doc.updated_at = datetime.now(timezone.utc)
            if getattr(admin_doc, "id", None) is None:
                admin_doc.created_at = datetime.now(timezone.utc)
                await admin_doc.insert()
            else:
                await admin_doc.save()

            # For response, decrypt the stored profile
            dec_admin = admin_doc.decrypt_fields(client_encryption)
            admin_profile = dec_admin.get("profile")
        elif admin_doc:
            # No change requested, just return existing decrypted profile
            dec_admin = admin_doc.decrypt_fields(client_encryption)
            admin_profile = dec_admin.get("profile")

    # Decrypt user fields for response
    full_name = _decrypt_to_str(client_encryption, user.full_name)
    email = _decrypt_to_str(client_encryption, user.email)
    phone = _decrypt_to_str(client_encryption, user.phone)

    return ProfileResponse(
        id=str(user.id),
        full_name=full_name,
        email=email,
        phone=phone,
        role=role_val,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        admin_profile=admin_profile,
    )


@router.post("/auth/profile/photo")
async def upload_profile_photo(
    request: Request,
    file: UploadFile = File(...),
):
    # Authenticate user
    user, _ = await _get_user_from_authorization(request)

    client_encryption = request.app.client_encryption
    dek_id = request.app.dek_id

    role_val = _decrypt_to_str(client_encryption, user.role)
    if role_val != "admin":
        raise HTTPException(status_code=403, detail="Only admin users can upload profile photos")

    # Validate & save image
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    ext = file.filename.split(".")[-1].lower()
    if ext not in ["png", "jpg", "jpeg", "gif", "webp"]:
        raise HTTPException(status_code=400, detail="Invalid image format")

    data = await file.read()
    full_name = _decrypt_to_str(client_encryption, user.full_name) or str(user.id)
    folder = f"{full_name.strip().lower()} profile"
    filename = safe_filename(file.filename)
    bucket = get_bucket_name()
    s3 = s3_client()
    key = f"{folder}/{filename}"
    put_object(s3, bucket, key, data, file.content_type)
    photo_url = presign(s3, bucket, key)

    # Load or build admin profile
    admin_doc = await Admin.find_one(Admin.user_id == str(user.id))

    profile_obj: AdminProfile
    if admin_doc and admin_doc.profile:
        # Decrypt existing profile
        decrypted_raw = decrypt_value(client_encryption, admin_doc.profile)
        if isinstance(decrypted_raw, (bytes, bytearray)):
            decrypted_raw = decrypted_raw.decode("utf-8")
            try:
                profile_dict = json.loads(decrypted_raw)
            except json.JSONDecodeError:
                profile_dict = {}
        elif isinstance(decrypted_raw, str):
            try:
                profile_dict = json.loads(decrypted_raw)
            except json.JSONDecodeError:
                profile_dict = {}
        elif isinstance(decrypted_raw, dict):
            profile_dict = decrypted_raw
        else:
            profile_dict = {}

        profile_obj = AdminProfile.model_validate(profile_dict)
    else:
        profile_obj = _build_default_admin_profile_for_user(user, client_encryption)

    # Update photo_url
    profile_obj.personal.personal_information.photo_url = photo_url

    profile_data = profile_obj.model_dump(mode="json", serialize_as_any=True)
    encrypted_profile = encrypt_value(client_encryption, dek_id, profile_data)

    if not admin_doc:
        admin_doc = Admin(user=user, user_id=str(user.id))

    admin_doc.profile = encrypted_profile
    now = datetime.now(timezone.utc)
    if getattr(admin_doc, "id", None) is None:
        admin_doc.created_at = now
        admin_doc.updated_at = now
        await admin_doc.insert()
    else:
        admin_doc.updated_at = now
        await admin_doc.save()

    return {"photo_url": photo_url}


@router.post("/auth/set-mpin")
async def set_mpin(payload: MPINSetRequest, request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = auth.split(" ", 1)[1]
    secret, alg, _ = _get_jwt_settings()
    try:
        decoded = jwt.decode(token, secret, algorithms=[alg])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    jti = decoded.get("jti")
    revoked = getattr(request.app, "revoked_jti", set())
    if jti in revoked:
        raise HTTPException(status_code=401, detail="Token revoked")

    user_id = decoded.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token subject")

    if payload.mpin != payload.confirm_mpin:
        raise HTTPException(status_code=400, detail="MPIN mismatch")

    client_encryption = request.app.client_encryption
    user = await UserDoc.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    hashed_mpin = hash_password(payload.mpin)
    enc_mpin = encrypt_value_deterministic(client_encryption, request.app.dek_id, hashed_mpin)
    enc_mpin_index = encrypt_value_deterministic(client_encryption, request.app.dek_id, payload.mpin)
    enc_deviceid_index = encrypt_value_deterministic(client_encryption, request.app.dek_id, payload.device_id)
    user.mpin = enc_mpin
    user.mpin_index = enc_mpin_index
    user.device_id = enc_deviceid_index
    await user.save()

    await log_audit(
        request=request,
        user_id=str(user.id),
        action="SET_MPIN",
        resource="auth",
        resource_id=str(user.id),
        status="success",
        notes="MPIN set"
    )

    return {"message": "MPIN set"}


@router.post("/auth/change-password")
async def change_password(payload: ChangePasswordRequest, request: Request):
    user, _ = await _get_user_from_authorization(request)
    client_encryption = request.app.client_encryption
    stored = _decrypt_to_str(client_encryption, user.password)
    if not stored or not verify_password(payload.current_password, stored):
        raise HTTPException(status_code=401, detail="Invalid current password")
    if payload.new_password != payload.confirm_new_password:
        raise HTTPException(status_code=400, detail="Password mismatch")
    new_hashed = hash_password(payload.new_password)
    user.password = encrypt_value(client_encryption, request.app.dek_id, new_hashed)
    await user.save()
    await log_audit(
        request=request,
        user_id=str(user.id),
        action="CHANGE_PASSWORD",
        resource="auth",
        resource_id=str(user.id),
        status="success",
        notes="Password changed"
    )
    return {"message": "Password changed"}


@router.post("/auth/forgot-setpin")
async def forgot_setpin(payload: ForgotMPINSetRequest, request: Request):
    user = await _authenticate_user(payload.email, payload.password, request)
    if payload.mpin != payload.confirm_mpin:
        raise HTTPException(status_code=400, detail="MPIN mismatch")
    client_encryption = request.app.client_encryption
    hashed_mpin = hash_password(payload.mpin)
    enc_mpin = encrypt_value_deterministic(client_encryption, request.app.dek_id, hashed_mpin)
    enc_mpin_index = encrypt_value_deterministic(client_encryption, request.app.dek_id, payload.mpin)
    enc_deviceid_index = encrypt_value_deterministic(client_encryption, request.app.dek_id, payload.device_id)
    user.mpin = enc_mpin
    user.mpin_index = enc_mpin_index
    user.device_id = enc_deviceid_index
    await user.save()
    await log_audit(
        request=request,
        user_id=str(user.id),
        action="FORGOT_SETPIN",
        resource="auth",
        resource_id=str(user.id),
        status="success",
        notes="MPIN reset via credentials"
    )
    return {"message": "MPIN updated"}


@router.post("/auth/forgot-password/request")
async def forgot_password_request(payload: ForgotPasswordRequest, request: Request):
    user = await _get_user_by_email(payload.email, request)
    import secrets
    otp = "".join([str(secrets.randbelow(10)) for _ in range(6)])
    otp_hash = hash_password(otp)
    reset = PasswordReset(
        user=user,
        user_id=str(user.id),
        email=str(payload.email),
        otp_hash=otp_hash,
    )
    await reset.insert()
    html = f"<p>Your password reset code is <b>{otp}</b>. It expires in 10 minutes.</p>"
    text = f"Your password reset code is {otp}. It expires in 10 minutes."
    try:
        send_email(str(payload.email), "Password Reset Code", html, text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    await log_audit(
        request=request,
        action="FORGOT_PASSWORD_REQUEST",
        resource="auth",
        resource_id=str(user.id),
        status="success",
        notes="OTP sent"
    )
    return {"message": "OTP sent", "reset_id": str(reset.id)}


@router.post("/auth/forgot-password/verify")
async def forgot_password_verify(payload: ForgotPasswordVerifyRequest, request: Request):
    now = datetime.now(timezone.utc)
    resets = await PasswordReset.find(PasswordReset.used == False).sort("-created_at").to_list()
    target = None
    for r in resets:
        exp = r.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now <= exp and verify_password(payload.otp, r.otp_hash):
            target = r
            break
    if not target:
        raise HTTPException(status_code=401, detail="Invalid or expired code")
    target.verified = True
    await target.save()
    await log_audit(
        request=request,
        user_id=str(target.user_id),
        action="FORGOT_PASSWORD_VERIFY",
        resource="auth",
        resource_id=str(target.user_id),
        status="success",
        notes="OTP verified"
    )
    return {"message": "OTP verified"}


@router.post("/auth/forgot-password/reset")
async def forgot_password_reset(payload: ForgotPasswordResetRequest, request: Request):
    now = datetime.now(timezone.utc)
    resets = await PasswordReset.find(PasswordReset.used == False, PasswordReset.verified == True).sort("-created_at").to_list()
    target = None
    for r in resets:
        exp = r.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now <= exp:
            target = r
            break
    if not target:
        raise HTTPException(status_code=400, detail="No verified reset found or code expired")
    if payload.new_password != payload.confirm_new_password:
        raise HTTPException(status_code=400, detail="Password mismatch")
    user = await UserDoc.get(target.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    client_encryption = request.app.client_encryption
    new_hashed = hash_password(payload.new_password)
    user.password = encrypt_value(client_encryption, request.app.dek_id, new_hashed)
    await user.save()
    target.used = True
    await target.save()
    await log_audit(
        request=request,
        user_id=str(user.id),
        action="FORGOT_PASSWORD_RESET",
        resource="auth",
        resource_id=str(user.id),
        status="success",
        notes="Password reset after OTP verify"
    )
    return {"message": "Password updated"}


# @router.post("/auth/login-mpin", response_model=TokenResponse)
# async def login_mpin(payload: MPINLoginRequest, request: Request):
#     client_encryption = request.app.client_encryption
#     dek_id = request.app.dek_id
#     secret, alg, ttl_min = _get_jwt_settings()

#     enc_email = encrypt_value_deterministic(client_encryption, dek_id, payload.email)
#     user = await UserDoc.find_one({"email": enc_email})
#     if not user:
#         raise HTTPException(status_code=401, detail="Invalid credentials")
#     if not user.is_active:
#         raise HTTPException(status_code=403, detail="User inactive")
#     if not user.mpin:
#         raise HTTPException(status_code=400, detail="MPIN not set")

#     stored = decrypt_value(client_encryption, user.mpin)
#     if isinstance(stored, bytes):
#         stored = stored.decode("utf-8")
#     if not verify_password(payload.mpin, stored):
#         raise HTTPException(status_code=401, detail="Invalid credentials")

#     now = datetime.now(timezone.utc)
#     exp = now + timedelta(minutes=ttl_min)
#     jti = str(uuid4())

#     role_val = None
#     if user.role:
#         r = decrypt_value(client_encryption, user.role)
#         role_val = r.decode("utf-8") if isinstance(r, bytes) else r

#     claims = {
#         "sub": str(user.id),
#         "email": payload.email,
#         "role": role_val,
#         "iat": int(now.timestamp()),
#         "exp": int(exp.timestamp()),
#         "jti": jti,
#     }

#     token = jwt.encode(claims, secret, algorithm=alg)

#     await log_audit(
#         request=request,
#         action="LOGIN_MPIN",
#         resource="auth",
#         resource_id=str(user.id),
#         status="success",
#         notes="User logged in via MPIN"
#     )

#     return TokenResponse(access_token=token, token_type="bearer")


@router.post("/auth/login-mpin-only", response_model=TokenResponse)
async def login_mpin_only(payload: MPINOnlyLoginRequest, request: Request):
    client_encryption = request.app.client_encryption
    dek_id = request.app.dek_id

    enc_index = encrypt_value_deterministic(client_encryption, dek_id, payload.mpin)
    users = await UserDoc.find({"mpin_index": enc_index}).to_list()
    if not users:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if len(users) > 1:
        raise HTTPException(status_code=409, detail="Multiple users with same MPIN")

    user = users[0]
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User inactive")

    stored = decrypt_value(client_encryption, user.mpin) if user.mpin else None
    if isinstance(stored, bytes):
        stored = stored.decode("utf-8")
    if not stored or not verify_password(payload.mpin, stored):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user.is_mpin = True
    
    await user.save()
    email_val = _decrypt_to_str(client_encryption, user.email)
    token = _generate_token_for_user(user, email_val, request)

    await log_audit(
        request=request,
        user_id=str(user.id),
        action="LOGIN_MPIN_ONLY",
        resource="auth",
        resource_id=str(user.id),
        status="success",
        notes="User logged in via MPIN only"
    )

    return TokenResponse(access_token=token, token_type="bearer")

