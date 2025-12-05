from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.startup import startup_app, shutdown_app
from app.accounts.routers.patient_router import router as patient_router
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

app.include_router(patient_router) 
app.include_router(user_router) 
app.include_router(auth_router)
app.include_router(facility_router)
app.include_router(campusblock_router)
app.include_router(facility_floor_router)
app.include_router(facility_department_router)
app.include_router(facility_room_router) 
app.include_router(bed_router) 
app.include_router(keycontact_router) 
app.include_router(pharmacy_router) 
app.include_router(laboratory_router) 
app.include_router(imaging_center_router)   
app.include_router(network_config_router)   
app.include_router(wifi_network_router)
app.include_router(work_station_router)
app.include_router(device_router)
app.include_router(interoperability_router)