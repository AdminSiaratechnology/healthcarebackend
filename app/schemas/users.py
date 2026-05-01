from pydantic import BaseModel, EmailStr
from typing import Optional
from app.accounts.models.user import UserRole
from app.schemas.admin import AdminProfile

class Users(BaseModel):
    full_name : str
    email : Optional[EmailStr] = None
    phone : Optional[str] = None
    role : UserRole
    password : Optional[str] = None
    admin_profile: Optional[AdminProfile] = None


class AdminUpdateSchema(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    

