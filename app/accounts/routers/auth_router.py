from fastapi import APIRouter, Request, HTTPException, Depends
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Optional, Tuple
import base64
import io
import pyotp
import qrcode
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
)
from app.accounts.models.user import UserDoc
from app.auth.password import verify_password, hash_password
from app.utils.audit import log_audit
from app.encryption.encryption import encrypt_value_deterministic, decrypt_value, encrypt_value
from app.database.config import settings


# router = APIRouter()
router = APIRouter(prefix="/account", tags=["Account"])


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


@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request):
    user = await _authenticate_user(payload.email, payload.password, request)
    token = _generate_token_for_user(user, payload.email, request)

    await log_audit(
        request=request,
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

    return ProfileResponse(
        id=str(user.id),
        full_name=full_name,
        email=email,
        phone=phone,
        role=role_val,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


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
        action="SET_MPIN",
        resource="auth",
        resource_id=str(user.id),
        status="success",
        notes="MPIN set"
    )

    return {"message": "MPIN set"}


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
        action="LOGIN_MPIN_ONLY",
        resource="auth",
        resource_id=str(user.id),
        status="success",
        notes="User logged in via MPIN only"
    )

    return TokenResponse(access_token=token, token_type="bearer")

