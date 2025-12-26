
from pydantic import BaseModel
from typing import Optional

class TransportVendorSchema(BaseModel):
    vendor_name: Optional[str] = None
    contact_number: Optional[str] = None
   