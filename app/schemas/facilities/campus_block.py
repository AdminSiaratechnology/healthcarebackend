from pydantic import BaseModel
from typing import Optional


class CampusBlockSchema(BaseModel):
    block_code: Optional[str] = None
    block_name: Optional[str] = None
