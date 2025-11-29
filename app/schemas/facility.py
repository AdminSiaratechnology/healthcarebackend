from pydantic import BaseModel, EmailStr, HttpUrl
from typing import Optional, List
# from app.facility.models.facility import FacilityType


from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from beanie import init_beanie, Document, Indexed
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, HttpUrl
from typing import Optional, List, Literal
from datetime import datetime
from decimal import Decimal
import os
import uuid
import json

class Address(BaseModel):
    street_address: str
    city: str
    state: str = Field(..., min_length=2, max_length=2)
    zip_code: str
    county: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None

class Branding(BaseModel):
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color : Optional[str] = None
    brand_notes : Optional[str] = None
    
class Wing(BaseModel):
    name: str
    floors: int = Field(..., ge=1)

class Room(BaseModel):
    room_number: str
    bed_count: int = Field(..., ge=1, le=4)
    room_type: Literal["Private", "Semi-Private", "Ward"] = "Semi-Private"
    is_available: bool = True

class Bed(BaseModel):
    bed_number: str
    is_occupied: bool = False

class KeyContact(BaseModel):
    role: str
    name: str
    phone: str
    email: Optional[EmailStr] = None
    is_primary: bool = False

class Partner(BaseModel):
    name: str
    type: Literal["Pharmacy", "Lab", "Imaging", "Therapy", "Hospice", "Other"]
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None

class Workstation(BaseModel):
    workstation_id: str
    location: str
    device_type: Literal["Desktop", "Laptop", "Tablet", "Nursing Station"]
    ip_address: Optional[str] = None

class Interoperability(BaseModel):
    ehr_system: Optional[str] = None
    hl7_enabled: bool = False
    fhir_enabled: bool = False


class Regulatory(BaseModel):
    license_number: Optional[str] = None
    medicare_provider_number: Optional[str] = None
    certified_beds: Optional[int] = None
    star_rating: Optional[int] = Field(None, ge=1, le=5)