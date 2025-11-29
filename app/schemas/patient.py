from pydantic import BaseModel


class Patient(BaseModel):
    name: str
    ssn: str
    phone: str