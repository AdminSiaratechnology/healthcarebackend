from pydantic import BaseModel, EmailStr
from typing import Optional
from app.accounts.models.user import UserRole

class Users(BaseModel):
    full_name : str
    email : Optional[EmailStr] = None
    phone : Optional[str] = None
    role : UserRole
    password : Optional[str] = None

