from fastapi import APIRouter, Depends, HTTPException, Request

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_dict, ensure_data_key, init_encryption
from app.schemas.scheduler.scheduler import SchedulerCreate, SchedulerResponse
from app.scheduler.models import Scheduler
from app.utils.audit import log_audit


router = APIRouter(prefix="/scheduler", tags=["scheduler"])

@router.post("/", response_model=SchedulerResponse)
async def create_scheduler(
    payload: SchedulerCreate,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

):
    try:
        # 1️⃣ User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        # 2️⃣ Encryption init
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce
        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id
        
        normalized_first_name = payload.first_name.strip().lower()
        normalized_middle_name = payload.middle_name.strip().lower() if payload.middle_name else ""
        normalized_last_name = payload.last_name.strip().lower()
        normalized_email = payload.email.strip().lower()
        normalized_full_name = f"{normalized_first_name} {normalized_middle_name} {normalized_last_name}".strip()
        normalized_phone = payload.phone.strip() if payload.phone else None

         # 6️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        existing = await UserDoc.find_one(
            (UserDoc.email_search == normalized_email) 
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="User with this email already exists"
            )
        
        # 7️⃣ Random encryption (actual storage)
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "first_name": payload.first_name,
                "middle_name": payload.middle_name,
                "last_name": payload.last_name,
                "full_name": f"{payload.first_name} {payload.middle_name or ''} {payload.last_name}".strip(),
                "email": payload.email,
                "phone": payload.phone,  # ✅ FIXED
            }
        )
        # 8️⃣ Create record

        scheduler_user = UserDoc(
            
            full_name=encrypted["full_name"],
            email=encrypted["email"],
            phone=encrypted["phone"],
            email_search=normalized_email,
            full_name_search=normalized_full_name,
            phone_search=normalized_phone,
        )
        await scheduler_user.insert()
        scheduler = Scheduler(
            created_by=user,
            user = scheduler_user,
            first_name=encrypted["first_name"],
            middle_name=encrypted["middle_name"],
            last_name=encrypted["last_name"],
            first_name_search=normalized_first_name,
            middle_name_search=normalized_middle_name,
            last_name_search=normalized_last_name,
        )
        await scheduler.insert()
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="CREATE",
                resource="scheduler",
                resource_id=str(scheduler.id),
                status="success",
            )
        except Exception:
            pass
        return {
            "success": True,
            "message": "Scheduler created successfully",
            "data": {
                "scheduler_id": str(scheduler.id)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")


