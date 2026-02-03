from datetime import datetime, timezone, date
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key, encrypt_value_deterministic,encrypt_dict
from app.auth.password import hash_password
from app.accounts.models.user import UserRole
from app.utils.audit import log_audit
from app.schemas.schedule.schedule import ScheduleSchema
from app.provider.models.providers import Provider
from beanie import PydanticObjectId
from beanie.operators import In
import json
import os
from app.schedule.models.schedule import ScheduleDoc
from bson import ObjectId
from typing import Optional
from beanie.operators import In,RegEx,Or


router = APIRouter(prefix="/schedule", tags=["Schedule"])






@router.post("/create/")
async def create_schedule(
    payload: ScheduleSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # --------------------------------------------------
        # 1️⃣ Current User
        # --------------------------------------------------
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # --------------------------------------------------
        # 2️⃣ Encryption Init (singleton style)
        # --------------------------------------------------
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        # --------------------------------------------------
        # 3️⃣ Facility validation (ownership)
        # --------------------------------------------------
        try:
            facility_obj_id = ObjectId(payload.facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid facility_id")

        facility = await Facility.find_one(
            Facility.id == facility_obj_id,
            Facility.created_by.id == user.id,
            # Facility.is_deleted == False,
        )

        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        
        # --------------------------------------------------
        # 4️⃣ Provider validation
        # --------------------------------------------------
        try:
            provider_obj_id = ObjectId(payload.provider_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid provider_id")

        provider = await Provider.find_one(
            Provider.id == provider_obj_id,
            Provider.is_deleted == False,
            Provider.status == "active",
            fetch_links=True,   # ✅ THIS is what you want
        )

        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        # Optional: provider belongs to facility
        if provider.facility_ids:
            provider_facility_ids = [str(f.id) for f in provider.facility_ids]

            if str(facility.id) not in provider_facility_ids:
                raise HTTPException(
                    status_code=400,
                    detail="Provider does not belong to this facility",
                )

        # --------------------------------------------------
        # 5️⃣ Duplicate Schedule Check (same provider + date)
        # --------------------------------------------------
        existing = await ScheduleDoc.find_one(
            ScheduleDoc.facility_id.id == facility.id,
            ScheduleDoc.provider_id.id == provider.id,
            ScheduleDoc.is_deleted == False,
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Schedule already exists for this provider in this facility",
            )

        # --------------------------------------------------
        # 6️⃣ Encrypt Payload
        # --------------------------------------------------
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "selected_date": str(payload.selected_date),
                "department": payload.department.value,
                "is_create_recurring_shift": payload.is_create_recurring_shift,
            },
        )

        shift_time_enc = None
        if payload.shift_time:
            shift_time_enc = encrypt_value(
                ce,
                dek_id,
                json.dumps(payload.shift_time.model_dump(), default=str),
            )

        # --------------------------------------------------
        # 7️⃣ Create Schedule Document
        # --------------------------------------------------
        schedule_doc = ScheduleDoc(
            facility_id=facility,
            provider_id=provider,
            created_by=user,

            selected_date=encrypted["selected_date"],
            department=encrypted["department"],
            is_create_recurring_shift=encrypted["is_create_recurring_shift"],
            shift_time=shift_time_enc,

            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await schedule_doc.insert()

        return {
            "success": True,
            "message": "Schedule created successfully",
            "schedule_id": str(schedule_doc.id),
            "facility_id": str(facility.id),
            "provider_id": str(provider.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Schedule Create Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating schedule",
        )



# @router.get("/get/{schedule_id}/")
# async def get_schedule_by_id(
#     schedule_id: str,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce

#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         sched = None
#         try:
#             s_oid = PydanticObjectId(schedule_id)
#             sched = await ScheduleDoc.get(s_oid)
#             facility_id = sched.facility_id.ref.id
#             provider_id = sched.provider_id.ref.id
#         except Exception:
#             sched = await ScheduleDoc.get(schedule_id)

#         if not sched:
#             raise HTTPException(status_code=404, detail="Schedule not found")

#         shift = _decrypt_json_field(ce, sched.shift_time)
#         result = {
#             "id": str(sched.id),
#             "facility_id": str(facility_id),
#             "provider_id": str(provider_id),
#             "selected_date": _decrypt_value(ce, sched.selected_date),
#             "shift_time": shift,
#             "department": _decrypt_value(ce, sched.department),
#             "is_create_recurring_shift": _decrypt_value(ce, sched.is_create_recurring_shift),
#             "created_at": sched.created_at,
#             "updated_at": sched.updated_at,
#         }

#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Read",
#                 resource="Scheduler",
#                 resource_id=str(schedule_id),
#                 status="success",
#                 notes="Schedule fetched",
#             )
#         except Exception:
#             pass

#         return result
#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=current_user_id,
#                 action="Read",
#                 resource="Scheduler",
#                 resource_id=schedule_id,
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail=str(e))




@router.put("/update/{schedule_id}/")
async def update_schedule(
    schedule_id: str,
    payload: ScheduleSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # --------------------------------------------------
        # 1️⃣ Current User
        # --------------------------------------------------
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # --------------------------------------------------
        # 2️⃣ Encryption Init
        # --------------------------------------------------
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        # --------------------------------------------------
        # 3️⃣ Validate Schedule
        # --------------------------------------------------
        try:
            schedule_obj_id = ObjectId(schedule_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid schedule_id")

        schedule = await ScheduleDoc.find_one(
            ScheduleDoc.id == schedule_obj_id,
            ScheduleDoc.created_by.id == user.id,
            ScheduleDoc.is_deleted == False,
            fetch_links=True,
        )

        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        # --------------------------------------------------
        # 4️⃣ Facility Validation
        # --------------------------------------------------
        try:
            facility_obj_id = ObjectId(payload.facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid facility_id")

        facility = await Facility.find_one(
            Facility.id == facility_obj_id,
            Facility.created_by.id == user.id,
        )

        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        # --------------------------------------------------
        # 5️⃣ Provider Validation
        # --------------------------------------------------
        try:
            provider_obj_id = ObjectId(payload.provider_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid provider_id")

        provider = await Provider.find_one(
            Provider.id == provider_obj_id,
            Provider.is_deleted == False,
            Provider.status == "active",
            fetch_links=True,
        )

        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        # provider belongs to facility
        if provider.facility_ids:
            provider_facility_ids = [str(f.id) for f in provider.facility_ids]
            if str(facility.id) not in provider_facility_ids:
                raise HTTPException(
                    status_code=400,
                    detail="Provider does not belong to this facility",
                )

        # --------------------------------------------------
        # 6️⃣ Duplicate Check (ignore current schedule)
        # --------------------------------------------------
        duplicate = await ScheduleDoc.find_one(
            ScheduleDoc.id != schedule.id,
            ScheduleDoc.facility_id.id == facility.id,
            ScheduleDoc.provider_id.id == provider.id,
            ScheduleDoc.is_deleted == False,
        )

        if duplicate:
            raise HTTPException(
                status_code=400,
                detail="Another schedule already exists for this provider in this facility",
            )

        # --------------------------------------------------
        # 7️⃣ Encrypt Updated Fields
        # --------------------------------------------------
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "selected_date": str(payload.selected_date),
                "department": payload.department.value,
                "is_create_recurring_shift": payload.is_create_recurring_shift,
            },
        )

        shift_time_enc = None
        if payload.shift_time:
            shift_time_enc = encrypt_value(
                ce,
                dek_id,
                json.dumps(payload.shift_time.model_dump(), default=str),
            )

        # --------------------------------------------------
        # 8️⃣ Update Schedule
        # --------------------------------------------------
        schedule.facility_id = facility
        schedule.provider_id = provider

        schedule.selected_date = encrypted["selected_date"]
        schedule.department = encrypted["department"]
        schedule.is_create_recurring_shift = encrypted["is_create_recurring_shift"]
        schedule.shift_time = shift_time_enc

        schedule.updated_at = datetime.now(timezone.utc)

        await schedule.save()

        return {
            "success": True,
            "message": "Schedule updated successfully",
            "schedule_id": str(schedule.id),
            "facility_id": str(facility.id),
            "provider_id": str(provider.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Schedule Update Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating schedule",
        )


@router.get("/list/")
async def list_schedules(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    from_date: date | None = Query(None, description="Filter start date (YYYY-MM-DD)"),
    to_date: date | None = Query(None, description="Filter end date (YYYY-MM-DD)"),

    facility_ids: list[str] | None = Query(None),
    provider_ids: list[str] | None = Query(None),

    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    try:
        # --------------------------------------------------
        # 1️⃣ Auth user
        # --------------------------------------------------
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # --------------------------------------------------
        # 2️⃣ Encryption instance
        # --------------------------------------------------
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        # --------------------------------------------------
        # 3️⃣ Base conditions
        # --------------------------------------------------
        conditions = [
            ScheduleDoc.created_by.id == user.id,
            ScheduleDoc.is_deleted == False,
        ]

        if status:
            conditions.append(ScheduleDoc.status == status.lower())

        # --------------------------------------------------
        # 4️⃣ Facility filter
        # --------------------------------------------------
        if facility_ids:
            try:
                facility_object_ids = [ObjectId(fid) for fid in facility_ids]
                conditions.append(
                    In(ScheduleDoc.facility_id.id, facility_object_ids)
                )
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid facility_ids")

        # --------------------------------------------------
        # 5️⃣ Provider filter
        # --------------------------------------------------
        if provider_ids:
            try:
                provider_object_ids = [ObjectId(pid) for pid in provider_ids]
                conditions.append(
                    In(ScheduleDoc.provider_id.id, provider_object_ids)
                )
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid provider_ids")

        # --------------------------------------------------
        # 6️⃣ Search filter
        # --------------------------------------------------
        if search:
            search_value = search.lower()
            conditions.append(
                Or(
                    RegEx(
                        ScheduleDoc.facility_id.facility_name_search,
                        f"^{search_value}"
                    ),
                    RegEx(
                        ScheduleDoc.provider_id.user.full_name_search,
                        f"^{search_value}"
                    ),
                )
            )

        # --------------------------------------------------
        # 7️⃣ Fetch data (NO pagination yet)
        # --------------------------------------------------
        schedules = await (
            ScheduleDoc.find(*conditions, fetch_links=True)
            .sort("-created_at")
            .to_list()
        )

        # --------------------------------------------------
        # 8️⃣ Date filter (Encrypted safe)
        # --------------------------------------------------
        filtered_schedules: list[ScheduleDoc] = []

        for schedule in schedules:
            if not schedule.selected_date:
                continue

            try:
                decrypted_date = decrypt_value(ce, schedule.selected_date)
                schedule_date = date.fromisoformat(decrypted_date)
            except Exception:
                continue

            if from_date and schedule_date < from_date:
                continue

            if to_date and schedule_date > to_date:
                continue

            filtered_schedules.append(schedule)

        # --------------------------------------------------
        # 9️⃣ Pagination AFTER filtering
        # --------------------------------------------------
        total = len(filtered_schedules)
        skip = (page - 1) * page_size
        paginated_schedules = filtered_schedules[skip: skip + page_size]

        # --------------------------------------------------
        # 🔟 Response mapping
        # --------------------------------------------------
        result = []
        for schedule in paginated_schedules:
            result.append({
                "id": str(schedule.id),
                "provider_id": str(schedule.provider_id.id),
                "provider_name": (
                    schedule.provider_id.user.full_name_search
                    if schedule.provider_id else None
                ),
                "facility_id": str(schedule.facility_id.id),
                "facility_name": (
                    schedule.facility_id.facility_name_search
                    if schedule.facility_id else None
                ),
                "department": decrypt_value(ce, schedule.department),
                "date": decrypt_value(ce, schedule.selected_date),
                "shift_time": (
                    json.loads(decrypt_value(ce, schedule.shift_time))
                    if schedule.shift_time else None
                ),
                "is_create_recurring_shift": decrypt_value(ce, schedule.is_create_recurring_shift),
                "status": schedule.status,
                "created_at": schedule.created_at,
                "updated_at": schedule.updated_at,
            })

        # --------------------------------------------------
        # 1️⃣1️⃣ Audit log (safe)
        # --------------------------------------------------
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Schedule",
                resource_id="LIST",
                status="success",
                notes=(
                    f"page={page}, page_size={page_size}, "
                    f"search={search}, status={status}, "
                    f"returned={len(result)}"
                ),
            )
        except Exception:
            pass

        # --------------------------------------------------
        # 1️⃣2️⃣ Final response
        # --------------------------------------------------
        return {
            "success": True,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "count": len(result),
            "total": total,
            "data": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")




