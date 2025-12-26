from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.database.config import settings
from app.encryption.encryption import init_encryption, ensure_data_key

from app.accounts.models.user import UserDoc
from app.accounts.models.admin import Admin
from app.patients.models.patients import PatientDoc
from app.accounts.models.password_reset import PasswordReset
from app.facility.models.facility import Facility
from app.facility.models.facility_branding import FacilityBranding
from app.facility.models.campusblock import CampusBlock
from app.facility.models.facility_floor import FacilityFloor
from app.facility.models.facility_department import FacilityDepartment
from app.facility.models.facility_rooms import FacilityRooms
from app.facility.models.beds import Beds
from app.facility.models.keycontact import KeyContact
from app.facility.models.facility_chargenurse import ChargeNursesDoc
from app.facility.models.emergency_contact import EmergencyContactDocs
from app.facility.models.pharmacies import Pharmacies
from app.facility.models.laboratory import Laboratory
from app.facility.models.imaging_center import ImagingCenter
from app.facility.models.network_config import NetworkConfig
from app.facility.models.wifi_network import WifiNetwork
from app.facility.models.workstations import WorkStation
from app.facility.models.DeviceInventory import DeviceInventory
from app.facility.models.interoperability import Interoperability
from app.facility.models.regulatory import RegulatoryInfoDoc
from app.facility.models.accreditations import AccerditationsDoc
from app.facility.models.state_reporting_identifiers import StateReportingIdentifiersDocs
from app.facility.models.standards import StandardsDoc
from app.facility.models.workflow import WorkflowDoc
from app.facility.models.transport_vendor import TransportVendorDocs
from app.facility.models.security import SecurityDoc
from app.facility.models.facility_breach_contact import BrachResponseContactDocs
from app.facility.models.quality import QualityDoc
from app.facility.models.quality_reporting import QualityReporting
from app.facility.models.attachments.floor_plans import FloorPlanDoc
from app.provider.models.providers import Provider
from app.provider.models.practice import Practice
from app.provider.models.clinical import clinical
from app.provider.models.security import Security
from app.provider.models.documents import ProviderDocuments
from app.patients.models.admissons import PatientAdmissionDoc
from app.patients.models.addressinfo import PatientAddressInfoDoc
from app.patients.models.insurance import PatientInsuranceDoc
from app.patients.models.emergency_contact import PatientEmergencyContactDoc
from app.patients.models.medical import PatientMedicalDoc
from app.clinicalmonitoring.models.category import CategoryDoc
from app.clinicalmonitoring.models.subcategory import SubcategoryDoc
from app.clinicalmonitoring.models.template_builder import TemplateBuilderDoc
from app.schedule.models.scheduler import SchedulerDoc
from app.prescriptions.models.prescription import PrescriptionDoc
from app.device.models.device import DeviceDoc
from app.PatientNotes.models.notes import PatientNotesDoc


from app.utils.audit import AuditLog

async def startup_app(app):
    app.mongodb = AsyncIOMotorClient(settings.MONGO_URI)
    app.db = app.mongodb[settings.DB_NAME]
    Facility.model_rebuild()
    await init_beanie(
        database=app.db,
        document_models=[
            
            AuditLog, 
            UserDoc, 
            PasswordReset,
            Facility,
            FacilityBranding,
            CampusBlock,
            FacilityFloor,
            FacilityDepartment,
            FacilityRooms,
            Beds,
            KeyContact,
            ChargeNursesDoc,
            EmergencyContactDocs,
            Pharmacies,
            Laboratory,
            ImagingCenter,
            NetworkConfig, 
            WifiNetwork,
            WorkStation,
            DeviceInventory,
            Interoperability,
            RegulatoryInfoDoc,
            AccerditationsDoc,
            StateReportingIdentifiersDocs,
            StandardsDoc,
            WorkflowDoc,
            TransportVendorDocs,
            SecurityDoc,
            BrachResponseContactDocs,
            QualityDoc,
            QualityReporting,
            FloorPlanDoc,
            Provider,
            Practice,
            clinical,
            Security,
            ProviderDocuments,
            PatientDoc,
            PatientAdmissionDoc,
            PatientAddressInfoDoc,
            PatientInsuranceDoc,
            PatientEmergencyContactDoc,
            PatientMedicalDoc,
            CategoryDoc,
            SubcategoryDoc,
            Admin,
            TemplateBuilderDoc,
            SchedulerDoc,
            PrescriptionDoc,
            DeviceDoc,
            PatientNotesDoc
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
