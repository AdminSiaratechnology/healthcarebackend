from pydantic import BaseModel, Field
from typing import Optional, List

class floorPlansSchema(BaseModel):
    plan_label : Optional[str] = None
    file_id : Optional[str] = None


class Policy(BaseModel):
    manual_title : Optional[str] = None
    file_id : Optional[str] = None


class Contract(BaseModel):
    contract_title : Optional[str] = None
    file_id : Optional[str] = None


class certificate(BaseModel):
    certificate_title = Optional[str] = None
    

    