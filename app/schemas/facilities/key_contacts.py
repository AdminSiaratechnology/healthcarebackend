from pydantic import BaseModel
from typing import Optional
from enum import Enum
from typing import List


class typeofdirector(str, Enum):
    Director = "Director"
    Administrator = "Administrator"
    
class DirectorOfNursingAndAdministrator(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    phone: Optional[str] = None
    extention: Optional[str] = None
    email: Optional[str] = None
    type: Optional[typeofdirector] = None


class MedicalDirector(BaseModel):
    name: Optional[str] = None
    speciality: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class AdmissionCoordinator(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class ITAdministrator(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

  


class KeyContacts(BaseModel):
    director_of_nursing_and_administrator: Optional[DirectorOfNursingAndAdministrator] = None
    medical_director: Optional[MedicalDirector] = None
    admission_coordinator: Optional[AdmissionCoordinator] = None
    it_administrator: Optional[ITAdministrator] = None
    # charge_nurse: Optional[chargeNurses] = None
    # emergency_contact: Optional[EmergencyContact] = None
    