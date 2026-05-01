from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class FieldSchema(BaseModel):
    name: str
    type: str   # text, number, dropdown, table
    required: Optional[bool] = False
    options: Optional[List[str]] = None   # dropdown
    columns: Optional[List[Dict[str, Any]]] = None  # table


class SubcategorySchema(BaseModel):
    name : str
    # description :Optional[str] = None
    # content : Optional[str] = None
    # fields: List[FieldSchema]
    # field: Optional[FieldSchema] = None 

