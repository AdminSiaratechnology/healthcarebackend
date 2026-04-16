from pydantic import BaseModel
from typing import Dict, Any


class PatientReportCreateSchema(BaseModel):
    patient_id: str
    template_id: str
    text: str   # 🎤 voice से आया हुआ text




class PatientReportResponseSchema(BaseModel):
    message: str
    data: Dict[str, Any]