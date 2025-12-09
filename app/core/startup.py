from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.database.config import settings
from app.encryption.encryption import init_encryption, ensure_data_key
from app.accounts.models.patient import PatientDoc
from app.accounts.models.user import UserDoc
from app.accounts.models.admin import Admin

from app.accounts.models.password_reset import PasswordReset
from app.facility.models.facility import Facility
from app.facility.models.facility_branding import FacilityBranding
from app.facility.models.campusblock import CampusBlock
from app.facility.models.facility_floor import FacilityFloor
from app.facility.models.facility_department import FacilityDepartment
from app.facility.models.facility_rooms import FacilityRooms
from app.facility.models.beds import Beds
from app.facility.models.keycontact import KeyContact
from app.facility.models.pharmacies import Pharmacies
from app.facility.models.laboratory import Laboratory
from app.facility.models.imaging_center import ImagingCenter
from app.facility.models.network_config import NetworkConfig
from app.facility.models.wifi_network import WifiNetwork
from app.facility.models.workstations import WorkStation
from app.facility.models.DeviceInventory import DeviceInventory
from app.facility.models.interoperability import Interoperability
from app.facility.models.regulatory import RegulatoryInfoDoc
from app.facility.models.standards import StandardsDoc
from app.facility.models.workflow import WorkflowDoc
from app.facility.models.security import SecurityDoc
from app.facility.models.quality import QualityDoc
from app.facility.models.attachments.floor_plans import FloorPlanDoc

from app.utils.audit import AuditLog

async def startup_app(app):
    app.mongodb = AsyncIOMotorClient(settings.MONGO_URI)
    app.db = app.mongodb[settings.DB_NAME]
    Facility.model_rebuild()
    await init_beanie(
        database=app.db,
        document_models=[
            PatientDoc, AuditLog, UserDoc, PasswordReset,
            Facility,
            FacilityBranding,
            CampusBlock,
            FacilityFloor,
            FacilityDepartment,
            FacilityRooms,
            Beds,
            KeyContact,
            Pharmacies,
            Laboratory,
            ImagingCenter,
            NetworkConfig, 
            WifiNetwork,
            WorkStation,
            DeviceInventory,
            Interoperability,
            RegulatoryInfoDoc,
            StandardsDoc,
            WorkflowDoc,
            SecurityDoc,
            QualityDoc,
            FloorPlanDoc,
            Admin
        ]
        )
     # Encryption init
    app.client_encryption = init_encryption()
    app.dek_id = ensure_data_key()
    app.revoked_jti = set()

    print("🚀 App started with Mongo + CSFLE ready")
async def shutdown_app(app):
    app.mongodb.close()
    app.client_encryption.close()
    print("🛑 App shutdown cleanly")
