from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.startup import startup_app, shutdown_app
from app.accounts.routers.user_router import router as user_router
from app.accounts.routers.auth_router import router as auth_router
from app.facility.routers.facility_router import router as facility_router
from app.facility.routers.campusblock_router import router as campusblock_router
from app.facility.routers.facility_floor_router import router as facility_floor_router
from app.facility.routers.department_router import router as facility_department_router
from app.facility.routers.facility_room_router import router as facility_room_router
from app.facility.routers.bed_router import router as bed_router
from app.facility.routers.keycontact_router import router as keycontact_router
from app.facility.routers.pharmacy_router import router as pharmacy_router
from app.facility.routers.laboratory_router import router as laboratory_router
from app.facility.routers.imaging_center_router import router as imaging_center_router
from app.facility.routers.network_config_router import router as network_config_router
from app.facility.routers.wifi_network_router import router as wifi_network_router
from app.facility.routers.work_station_router import router as work_station_router
from app.facility.routers.device_router import router as device_router
from app.facility.routers.interoperability_router import router as interoperability_router
from app.facility.routers.regulatory_router import router as regulatory_router
from app.facility.routers.accerditations_router import router as accerditations_router
from app.facility.routers.state_reporting_identifiers_router import router as state_reporting_identifiers_router
from app.facility.routers.standards_router import router as standards_router
from app.facility.routers.workflow_router import router as workflow_router
from app.facility.routers.transport_vendor_router import router as transport_vendor_router
from app.facility.routers.security_router import router as security_router
from app.facility.routers.breach_contact import router as breach_contact
from app.facility.routers.quality_router import router as quality_router
from app.facility.routers.quality_reporting_router import router as quality_reporting_router
from app.provider.router.provider_router import router as provider_router
from app.provider.router.practice_router import router as practice_router
from app.provider.router.clinical_router import router as clinical_router
from app.provider.router.security_router import router as provider_security_router
from app.provider.router.provider_documents_router import router as provider_documents_router
from app.patients.routers.patient_router import router as patient_router
from app.patients.routers.patient_admissions_router import router as patient_admissions_router 
from app.facility.routers.facility_charge_nurses_router import router as charge_nurse_router
from app.facility.routers.emergency_contact_router import router as emergency_contact_router
from app.patients.routers.patient_address_router import router as patient_address_router
from app.patients.routers.insurance_router import router as insurance_router
from app.patients.routers.emergency_contact_router import router as patient_emergency_contact_router
from app.patients.routers.medical_router import router as patient_medical_router
from app.clinicalmonitoring.routers.category_router import router as category_router
from app.clinicalmonitoring.routers.subcategory_router import router as subcategory_router
from app.clinicalmonitoring.routers.template_builder_router import router as template_builder_router
from app.schedule.router.scheduler_router import router as scheduler_router
from app.prescriptions.router.prescription_router import router as prescription_router
from app.device.router.device_router import router as devices_router
from app.PatientNotes.routers.notes_router import router as notes_router
from app.ShiftManagement.routers.shift_router import router as shiftmanagement_router
from app.FacilityRole.routers.user_facility_router import router as user_facility_router



from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup_app(app) 
    yield
    await shutdown_app(app)


app = FastAPI(lifespan=lifespan)   


origins = [
    "http://localhost:63970",   # ✅ no slash
    "http://localhost:53418",  # ✅ no slash
    "http://localhost:5173",
    "https://your-frontend-domain.com" 
]



app.add_middleware(
    CORSMiddleware,
    # allow_origins=origins,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(user_router) 
app.include_router(auth_router)
app.include_router(facility_router)
app.include_router(campusblock_router)
app.include_router(facility_floor_router)
app.include_router(facility_department_router)
app.include_router(facility_room_router) 
app.include_router(bed_router) 
app.include_router(keycontact_router) 
app.include_router(charge_nurse_router)
app.include_router(emergency_contact_router)
app.include_router(pharmacy_router) 
app.include_router(laboratory_router) 
app.include_router(imaging_center_router)   
app.include_router(network_config_router)   
app.include_router(wifi_network_router)
app.include_router(work_station_router)
app.include_router(device_router)
app.include_router(interoperability_router)
app.include_router(regulatory_router)
app.include_router(accerditations_router)
app.include_router(state_reporting_identifiers_router)

app.include_router(standards_router)
app.include_router(workflow_router)
app.include_router(transport_vendor_router)
app.include_router(security_router)
app.include_router(breach_contact)
app.include_router(quality_router)
app.include_router(quality_reporting_router)
app.include_router(provider_router)
app.include_router(practice_router)
app.include_router(clinical_router)
app.include_router(provider_security_router)
app.include_router(provider_documents_router)
app.include_router(patient_router)
app.include_router(patient_admissions_router)
app.include_router(patient_address_router)
app.include_router(insurance_router)
app.include_router(patient_emergency_contact_router)
app.include_router(patient_medical_router)

# --------------------------------- Category -------------------------------------

app.include_router(category_router)

# --------------------------------------- Subcategory -------------------------------

app.include_router(subcategory_router)


# -------------------------------------- TemplateBuilder -------------------------------


app.include_router(template_builder_router)


# --------------------------- Scheduler ------------------------------------

app.include_router(scheduler_router)


# --------------------------- Prescription ------------------------------------

app.include_router(prescription_router)






# --------------------------- Devices ------------------------------------

app.include_router(devices_router)
app.include_router(notes_router)



# ---------------------------- Shift Management ------------------------------------

app.include_router(shiftmanagement_router)
app.include_router(user_facility_router)







