from pydantic import BaseModel
from typing import Optional


class PharmaciesSchema(BaseModel):
    pharmacy_name:  Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    fax: Optional[str] = None
    after_hours_phone: Optional[str] = None
    contract_file_id: Optional[str] = None
    delivery_schedule: Optional[str] = None
    