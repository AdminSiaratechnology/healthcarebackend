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
from app.patients.models.patients import PatientDoc
from bson import ObjectId
from typing import Optional, List
from beanie.operators import And, Or, In, RegEx


router = APIRouter(prefix="/schedule", tags=["Schedule"])



@router.post("/create/")
async def create_schedule(
    payload: ScheduleSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # --------------------------------------------------
        # 1️⃣ Current User Validation
        # --------------------------------------------------
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # --------------------------------------------------
        # 2️⃣ Encryption Init (Singleton Style)
        # --------------------------------------------------
        if not hasattr(request.app, "client_encryption"):
            request.app.client_encryption = init_encryption()

        if not hasattr(request.app, "dek_id"):
            request.app.dek_id = ensure_data_key()

        # --------------------------------------------------
        # 3️⃣ Extract Payload Values (IMPORTANT: Before Use)
        # --------------------------------------------------
        selected_date = payload.selected_date.isoformat()
        slot_time = payload.slot_time.strftime("%H:%M:%S")
       


        # --------------------------------------------------
        # 4️⃣ Facility Validation (Ownership Check)
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

        # Optional: Ensure provider belongs to facility
        if provider.facility_ids:
            provider_facility_ids = [str(f.id) for f in provider.facility_ids]
            if str(facility.id) not in provider_facility_ids:
                raise HTTPException(
                    status_code=400,
                    detail="Provider does not belong to this facility",
                )

        # --------------------------------------------------
        # 6️⃣ Patient Validation
        # --------------------------------------------------
        try:
            patient_obj_id = ObjectId(payload.patient_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid patient_id")

        patient = await PatientDoc.find_one(
            PatientDoc.id == patient_obj_id,
            PatientDoc.is_deleted == False,
            PatientDoc.status == "active",
        )

        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        # --------------------------------------------------
        # 7️⃣ Duplicate Schedule Check
        # (Matches your unique index)
        # --------------------------------------------------
        existing = await ScheduleDoc.find_one(
            ScheduleDoc.provider_id.id == provider.id,
            ScheduleDoc.schedule_date == selected_date,
            ScheduleDoc.slot_time == slot_time,
            ScheduleDoc.is_deleted == False,
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Schedule already exists for this provider at this time",
            )

        # --------------------------------------------------
        # 8️⃣ Create Schedule Document
        # --------------------------------------------------
        schedule_doc = ScheduleDoc(
            facility_id=facility,
            provider_id=provider,
            patient_id=patient,
            created_by=user,
            schedule_date=selected_date,
            slot_time=slot_time,
            
        )

        await schedule_doc.insert()

        # --------------------------------------------------
        # 9️⃣ Success Response
        # --------------------------------------------------
        return {
            "success": True,
            "message": "Schedule created successfully",
            "schedule_id": str(schedule_doc.id),
            "facility_id": str(facility.id),
            "provider_id": str(provider.id),
            "patient_id": str(patient.id),
        }

    except HTTPException:
        raise

    except Exception as e:
        print("❌ Schedule Create Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating schedule",
        )



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
            
        try:
            patient_obj_id = ObjectId(payload.patient_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid patient_id")

        patient = await PatientDoc.find_one(
            PatientDoc.id == patient_obj_id,
            PatientDoc.is_deleted == False,
            PatientDoc.status == "active",
        )

        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        # --------------------------------------------------
        # 6️⃣ Duplicate Check (ignore current schedule)
        # --------------------------------------------------
        duplicate = await ScheduleDoc.find_one(
            ScheduleDoc.id != schedule.id,
            ScheduleDoc.provider_id.id == provider.id,
            ScheduleDoc.schedule_date == payload.selected_date.isoformat(),
            ScheduleDoc.slot_time == payload.slot_time.strftime("%H:%M:%S"),
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
       
        # --------------------------------------------------
        # 8️⃣ Update Schedule
        # --------------------------------------------------
        selected_date = payload.selected_date.isoformat()
        slot_time = payload.slot_time.strftime("%H:%M:%S")

        schedule.facility_id = facility
        schedule.provider_id = provider
        schedule.patient_id = patient

        schedule.schedule_date = selected_date
        schedule.slot_time = slot_time

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

    from_date: Optional[date] = Query(None, description="Filter start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="Filter end date (YYYY-MM-DD)"),

    facility_ids: Optional[List[str]] = Query(None),
    provider_ids: Optional[List[str]] = Query(None),

    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    try:
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        conditions = [
            ScheduleDoc.created_by.id == user.id,
            ScheduleDoc.is_deleted == False,
        ]

        if status:
            conditions.append(ScheduleDoc.status == status.lower())

        # Facility filter
        if facility_ids:
            try:
                facility_object_ids = [ObjectId(fid) for fid in facility_ids]
                conditions.append(In(ScheduleDoc.facility_id.id, facility_object_ids))
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid facility_ids: {exc}")

        # Provider filter
        if provider_ids:
            try:
                provider_object_ids = [ObjectId(pid) for pid in provider_ids]
                conditions.append(In(ScheduleDoc.provider_id.id, provider_object_ids))
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid provider_ids: {exc}")

        # Search filter
        if search:
            search_value = search.lower().strip()
            conditions.append(
                Or(
                    RegEx(
                        ScheduleDoc.facility_id.facility_name_search,
                        f"^{search_value}",
                        options="i"
                    ),
                    RegEx(
                        ScheduleDoc.provider_id.user.full_name_search,
                        f"^{search_value}",
                        options="i"
                    ),
                )
            )

        # Date range filter – compare as ISO strings
        if from_date:
            conditions.append(ScheduleDoc.schedule_date >= from_date.isoformat())
        if to_date:
            conditions.append(ScheduleDoc.schedule_date <= to_date.isoformat())

        # Query with fetch_links
        query = ScheduleDoc.find(*conditions, fetch_links=True).sort("-created_at")

        total = await query.count()

        skip = (page - 1) * page_size
        schedules = await query.skip(skip).limit(page_size).to_list()

        # Response building
        result = []
        for schedule in schedules:
            provider = getattr(schedule, "provider_id", None)
            facility = getattr(schedule, "facility_id", None)

            result.append({
                "id": str(schedule.id),
                "provider_id": str(provider.id) if provider else None,
                "provider_name": (
                    provider.user.full_name_search
                    if provider and hasattr(provider.user, "full_name_search") else None
                ),
                "facility_id": str(facility.id) if facility else None,
                "facility_name": (
                    facility.facility_name_search
                    if facility and hasattr(facility, "facility_name_search") else None
                ),
                "date": schedule.schedule_date,
                "slot_time": schedule.slot_time,
                "status": schedule.status,
                "created_at": schedule.created_at.isoformat() if schedule.created_at else None,
                "updated_at": schedule.updated_at.isoformat() if schedule.updated_at else None,
            })

        # Optional audit log (comment out if not needed)
        # await log_audit(...)

        return {
            "success": True,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 1,
            "count": len(result),
            "data": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ List Schedules Error:", str(e))
        raise HTTPException(status_code=500, detail="Internal Server Error")
