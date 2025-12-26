from pydantic import BaseModel,EmailStr
from typing import Optional

class CategorySchema(BaseModel):
    name : str
