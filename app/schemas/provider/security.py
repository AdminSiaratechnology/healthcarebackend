from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class SecuritySchema(BaseModel):
    is_account_active: Optional[bool] = None
    is_sms_authentication: Optional[bool] = None
    is_sms_authentication : bool = None
