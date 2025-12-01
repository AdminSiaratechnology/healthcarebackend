from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from pydantic import field_validator

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

class ProfileResponse(BaseModel):
    id: str
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

class MPINSetRequest(BaseModel):
    mpin: str
    confirm_mpin: str
    device_id: Optional[str] = None


    @field_validator("mpin", "confirm_mpin")
    @classmethod
    def validate_mpin(cls, v: str):
        if not v.isdigit():
            raise ValueError("MPIN must be numeric")
        if len(v) < 4 or len(v) > 6:
            raise ValueError("MPIN must be 4-6 digits")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_new_password: str


class ForgotMPINSetRequest(BaseModel):
    email: EmailStr
    password: str
    mpin: str
    confirm_mpin: str
    device_id: Optional[str] = None

    @field_validator("mpin", "confirm_mpin")
    @classmethod
    def validate_mpin(cls, v: str):
        if not v.isdigit():
            raise ValueError("MPIN must be numeric")
        if len(v) < 4 or len(v) > 6:
            raise ValueError("MPIN must be 4-6 digits")
        return v


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordVerifyRequest(BaseModel):
    otp: str
    # new_password: str
    # confirm_new_password: str


class ForgotPasswordResetRequest(BaseModel):
    new_password: str
    confirm_new_password: str

class MPINLoginRequest(BaseModel):
    email: EmailStr
    mpin: str
    
    @field_validator("mpin")
    @classmethod
    def validate_login_mpin(cls, v: str):
        if not v.isdigit():
            raise ValueError("MPIN must be numeric")
        if len(v) < 4 or len(v) > 6:
            raise ValueError("MPIN must be 4-6 digits")
        return v

class MPINOnlyLoginRequest(BaseModel):
    mpin: str
   
    @field_validator("mpin")
    @classmethod
    def validate_only_mpin(cls, v: str):
        if not v.isdigit():
            raise ValueError("MPIN must be numeric")
        if len(v) < 4 or len(v) > 6:
            raise ValueError("MPIN must be 4-6 digits")
        return v


class GoogleAuthSetupRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthSetupResponse(BaseModel):
    secret: Optional[str] = None
    qr_code_png: Optional[str] = None
    is_already_enabled: bool = False


class GoogleAuthVerifyRequest(BaseModel):
    otp: str

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str):
        if not v.isdigit():
            raise ValueError("OTP must be numeric")
        if len(v) != 6:
            raise ValueError("OTP must be exactly 6 digits")
        return v
