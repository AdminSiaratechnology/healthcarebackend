from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.accounts.models.user import UserDoc, UserRole
from app.auth.deps import get_current_user_id
from app.auth.password import hash_password
from app.encryption.encryption import decrypt_value, encrypt_dict, encrypt_value_deterministic, ensure_data_key, init_encryption,encrypt_value
from app.schemas.scheduler.scheduler import SchedulerCreate, SchedulerResponse,PaginatedProductOut
from app.scheduler.models import Scheduler
from app.utils.audit import log_audit
from typing import Optional, List
from beanie.operators import RegEx,Or,In

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


        hashed_password = hash_password(payload.password) if payload.password else None

        deterministic_email = encrypt_value_deterministic(ce, dek_id, payload.email)

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
                "phone": payload.phone,  # ✅ FIXED
               
            }
        )
        # 8️⃣ Create record

        scheduler_user = UserDoc(
            
            full_name=encrypted["full_name"],
            email=deterministic_email,
            phone=encrypted["phone"],
            email_search=normalized_email,
            full_name_search=normalized_full_name,
            phone_search=normalized_phone,
            password=encrypt_value(ce, dek_id, hashed_password) if hashed_password else None,
            role=encrypt_value(ce, dek_id, UserRole.SCHEDULER.value),
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



# @router.get("/list/",response_model=PaginatedProductOut)
# async def get_all_schedulers(
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),

#     page: int = Query(1, ge=1),
#     page_size: int = Query(10, ge=1, le=100),

#     search: Optional[str] = Query(None),
#     status: Optional[str] = Query(None),
# ):
#     try:
#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")
#          # 2️⃣ Encryption
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce

#          # ----------------------------
#         # 3️⃣ Query conditions (Beanie style)
#         # ----------------------------
#         conditions = [
#             Scheduler.created_by.id == user.id,
#             Scheduler.is_deleted == False
#         ]
        
#         query = Scheduler.find(
#             Scheduler.created_by.id == current_user_id,
#             Scheduler.is_deleted == False
#         )

#         if status:
#             conditions.append(Scheduler.status == status.lower())

        
#         if search:
#             search_value = search.lower()
#             conditions.append(
#                 Or(
#                     RegEx(Scheduler.first_name_search, f"^{search_value}"),
#                     RegEx(Scheduler.last_name_search, f"^{search_value}"),
                   
#                 )
               
#             )
        
#         if search:
#             conditions.append(
#                 RegEx(Scheduler.first_name_search, f"^{search.lower()}")
#             )




@router.get("/list/", response_model=PaginatedProductOut)
async def get_all_schedulers(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    try:
        # 1️⃣ Current user
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 2️⃣ Encryption init
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        # 3️⃣ Query conditions
        conditions = [
            Scheduler.created_by.id == user.id,
            Scheduler.is_deleted == False
        ]
        if status:
            conditions.append(Scheduler.status == status.lower())
        if search:
            search_value = search.strip().lower()
            conditions.append(
                Or(
                    RegEx(Scheduler.first_name_search, f"^{search_value}"),
                    RegEx(Scheduler.last_name_search, f"^{search_value}")
                )
            )

        # 4️⃣ Pagination
        skip = (page - 1) * page_size

        # 5️⃣ Fetch schedulers
        schedulers_list = await (
            Scheduler.find(*conditions, fetch_links=True)
            .sort("-created_at")
            .skip(skip)
            .limit(page_size)
            .to_list()
        )
        total_count = await Scheduler.find(*conditions).count()

        # 6️⃣ Build response with decryption
        result: List[dict] = []
        for sched in schedulers_list:
            result.append({
                "id": str(sched.id),
                "first_name": decrypt_value(ce, sched.first_name),
                "middle_name": decrypt_value(ce, sched.middle_name) if sched.middle_name else None,
                "last_name": decrypt_value(ce, sched.last_name),
                "status": sched.status,
                "created_by": str(sched.created_by.id) if sched.created_by else None,
                "created_at": sched.created_at,
                "updated_at": sched.updated_at,
                "email": decrypt_value(ce, sched.user.email) if sched.user and sched.user.email else None,
                "phone": decrypt_value(ce, sched.user.phone) if sched.user and sched.user.phone else None,
            })

        # 7️⃣ Audit log
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="READ",
                resource="Scheduler",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Schedulers fetched | page={page}, page_size={page_size}, "
                    f"search={search}, status={status}, returned={len(result)}"
                ),
            )
        except Exception:
            pass

        # 8️⃣ Final response
        # return {
        #     "success": True,
        #     "page": page,
        #     "page_size": page_size,
        #     "total_pages": (total_count + page_size - 1) // page_size,
        #     "count": len(result),
        #     "total": total_count,
        #     "data": result,
        # }
        return PaginatedProductOut(
            total=total_count,
            page=page,
            limit=page_size,
            items=result
        )

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Scheduler List Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while fetching schedulers",
        )