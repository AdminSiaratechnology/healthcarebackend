from pydantic import BaseModel
from typing import Optional

class TemplateBuilderSchema(BaseModel):
    template_name : str
    short_name : Optional[str] = None
    discipline :Optional[str] = None
    

