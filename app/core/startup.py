from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.database.config import settings
from app.encryption.encryption import init_encryption, ensure_data_key
from app.accounts.models.patient import PatientDoc
from app.accounts.models.user import UserDoc
from app.facility.models.facility import Facility
from app.facility.models.branding import BrandingDoc
from app.facility.models.contacts import ContactsDoc
from app.facility.models.address import AddressDoc
from app.facility.models.basic import BasicDoc
from app.facility.models.structure import StructureDoc
from app.facility.models.rooms import RoomsDoc
from app.facility.models.rooms_beds import RoomsBedsDoc
from app.facility.models.partners import PartnersDoc
from app.facility.models.it_workstations import WorkstationsDoc
from app.facility.models.interoperability import InteroperabilityDoc
from app.facility.models.regulatory import RegulatoryDoc
from app.facility.models.key_contacts import KeyContactsDoc

from app.utils.audit import AuditLog

async def startup_app(app):
    app.mongodb = AsyncIOMotorClient(settings.MONGO_URI)
    app.db = app.mongodb[settings.DB_NAME]
    Facility.model_rebuild()
    await init_beanie(
        database=app.db,
        document_models=[
            PatientDoc, AuditLog, UserDoc,
            Facility,
            BrandingDoc, ContactsDoc, AddressDoc,
            BasicDoc, StructureDoc, RoomsDoc, RoomsBedsDoc,
            PartnersDoc, WorkstationsDoc, InteroperabilityDoc, RegulatoryDoc,
            KeyContactsDoc,
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
