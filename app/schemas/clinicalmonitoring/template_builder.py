from pydantic import BaseModel
from typing import Optional, List

class TemplateBuilderSchema(BaseModel):
    sub_category_ids: List[str]
    template_name : str
    short_name : Optional[str] = None
    discipline :Optional[str] = None

class TemplateBuilderUpdateSchema(BaseModel):
    sub_category_ids: Optional[List[str]] = None
    template_name : Optional[str] = None
    short_name : Optional[str] = None
    discipline :Optional[str] = None
    

