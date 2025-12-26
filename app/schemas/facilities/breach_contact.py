from pydantic import BaseModel,EmailStr
from typing import Optional

class BreachContactsSchema(BaseModel):
    name : Optional[str] = None
    Role : Optional[str] = None
    phone : Optional[str] = None
    email : Optional[EmailStr] = None
   