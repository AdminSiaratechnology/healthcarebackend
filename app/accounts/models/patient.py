from beanie import Document
from bson.binary import Binary
from pydantic import ConfigDict


class PatientDoc(Document):
    name: str
    ssn: Binary
    phone: Binary
    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        name = "patients"
    
