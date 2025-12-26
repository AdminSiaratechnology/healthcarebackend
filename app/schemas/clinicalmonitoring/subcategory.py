from pydantic import BaseModel
from typing import Optional

class SubcategorySchema(BaseModel):
    name : str
    description :Optional[str] = None
    content : Optional[str] = None

