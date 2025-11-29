from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.startup import startup_app, shutdown_app
from app.accounts.routers.patient_router import router as patient_router
from app.accounts.routers.user_router import router as user_router
from app.accounts.routers.auth_router import router as auth_router
from app.facility.routers.facility_router import router as facility_router
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
