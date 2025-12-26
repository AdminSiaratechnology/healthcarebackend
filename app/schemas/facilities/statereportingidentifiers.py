from pydantic import BaseModel
from typing import Optional

class StateReportingIdentifiersSchema(BaseModel):
    registry_system_name : Optional[str] = None
    identifier_value : Optional[str] = None
