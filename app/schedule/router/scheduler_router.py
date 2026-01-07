from datetime import datetime, timezone, date
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import ValidationError
from app.facility.models.facility import Facility

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key, encrypt_value_deterministic
from app.auth.password import hash_password
from app.accounts.models.user import UserRole
from app.utils.audit import log_audit
from app.schemas.schedule.schedule import ScheduleSchema
from app.provider.models.providers import Provider
from beanie import PydanticObjectId
import json
import os
from app.schedule.models.scheduler import SchedulerDoc

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw


def _decrypt_json_field(client_encryption, encrypted_val):
    val = _decrypt_value(client_encryption, encrypted_val)
    if not val:
        return None
    try:
        return json.loads(val) if isinstance(val, str) else val
    except Exception:
        return None


@router.post("/create/")
async def create_schedule(
    payload: ScheduleSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce
        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        facility_obj = None
        try:
            fac_oid = PydanticObjectId(payload.facility_id)
            facility_obj = await Facility.get(fac_oid)
        except Exception:
            facility_obj = await Facility.get(payload.facility_id)
        if not facility_obj:
            raise HTTPException(status_code=404, detail="Facility not found")

        provider_obj = None
        try:
            prov_oid = PydanticObjectId(payload.provider_id)
            provider_obj = await Provider.get(prov_oid)
        except Exception:
            provider_obj = await Provider.get(payload.provider_id)
        if not provider_obj:
            raise HTTPException(status_code=404, detail="Provider not found")

        sel_date_enc = encrypt_value(ce, dek_id, payload.selected_date.isoformat()) if payload.selected_date else None
        shift_payload = None
        if payload.shift_time is not None:
            try:
                shift_payload = json.dumps(payload.shift_time.model_dump(mode="json"))
            except Exception:
                shift_payload = json.dumps(payload.shift_time)
        shift_enc = encrypt_value(ce, dek_id, shift_payload) if shift_payload is not None else None
        dept_val = getattr(payload.department, "value", str(payload.department)) if payload.department is not None else None
        dept_enc = encrypt_value(ce, dek_id, dept_val) if dept_val is not None else None
        recurring_enc = encrypt_value(ce, dek_id, payload.is_create_recurring_shift) if payload.is_create_recurring_shift is not None else None

        doc = SchedulerDoc(
            provider_id=provider_obj,
            facility_id=facility_obj,
            selected_date=sel_date_enc,
            shift_time=shift_enc,
            department=dept_enc,
            is_create_recurring_shift=recurring_enc,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Scheduler",
                resource_id=str(doc.id),
                status="success",
                notes="Schedule created",
            )
        except Exception:
            pass

        return {"id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Create",
                resource="Scheduler",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get/{schedule_id}/")
async def get_schedule_by_id(
    schedule_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        sched = None
        try:
            s_oid = PydanticObjectId(schedule_id)
            sched = await SchedulerDoc.get(s_oid)
            facility_id = sched.facility_id.ref.id
            provider_id = sched.provider_id.ref.id
        except Exception:
            sched = await SchedulerDoc.get(schedule_id)

        if not sched:
            raise HTTPException(status_code=404, detail="Schedule not found")

        shift = _decrypt_json_field(ce, sched.shift_time)
        result = {
            "id": str(sched.id),
            "facility_id": str(facility_id),
            "provider_id": str(provider_id),
            "selected_date": _decrypt_value(ce, sched.selected_date),
            "shift_time": shift,
            "department": _decrypt_value(ce, sched.department),
            "is_create_recurring_shift": _decrypt_value(ce, sched.is_create_recurring_shift),
            "created_at": sched.created_at,
            "updated_at": sched.updated_at,
        }

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Scheduler",
                resource_id=str(schedule_id),
                status="success",
                notes="Schedule fetched",
            )
        except Exception:
            pass

        return result
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Read",
                resource="Scheduler",
                resource_id=schedule_id,
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))



@router.put("/update/{schedule_id}/")
async def update_schedule(
    schedule_id: str,
    payload: ScheduleSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce
        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        sched = None
        try:
            s_oid = PydanticObjectId(schedule_id)
            sched = await SchedulerDoc.get(s_oid)
        except Exception:
            sched = await SchedulerDoc.get(schedule_id)

        if not sched:
            raise HTTPException(status_code=404, detail="Schedule not found")

        facility_obj = None
        try:
            fac_oid = PydanticObjectId(payload.facility_id)
            facility_obj = await Facility.get(fac_oid)
        except Exception:
            facility_obj = await Facility.get(payload.facility_id)
        if not facility_obj:
            raise HTTPException(status_code=404, detail="Facility not found")

        provider_obj = None
        try:
            prov_oid = PydanticObjectId(payload.provider_id)
            provider_obj = await Provider.get(prov_oid)
        except Exception:
            provider_obj = await Provider.get(payload.provider_id)
        if not provider_obj:
            raise HTTPException(status_code=404, detail="Provider not found")

        sel_date_enc = encrypt_value(ce, dek_id, payload.selected_date.isoformat()) if payload.selected_date else None
        shift_payload = None
        if payload.shift_time is not None:
            try:
                shift_payload = json.dumps(payload.shift_time.model_dump(mode="json"))
            except Exception:
                shift_payload = json.dumps(payload.shift_time)
        shift_enc = encrypt_value(ce, dek_id, shift_payload) if shift_payload is not None else None
        dept_val = getattr(payload.department, "value", str(payload.department)) if payload.department is not None else None
        dept_enc = encrypt_value(ce, dek_id, dept_val) if dept_val is not None else None
        recurring_enc = encrypt_value(ce, dek_id, payload.is_create_recurring_shift) if payload.is_create_recurring_shift is not None else None 
        sched.provider_id = provider_obj
        sched.facility_id = facility_obj
        sched.selected_date = sel_date_enc
        sched.shift_time = shift_enc
        sched.department = dept_enc
        sched.is_create_recurring_shift = recurring_enc
        sched.updated_at = datetime.now(timezone.utc)
        await sched.save()
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Scheduler",
                resource_id=str(sched.id),
                status="success",
                notes="Schedule updated",
            )
        except Exception:
            pass        
        return {"id": str(sched.id)}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Update",
                resource="Scheduler",
                resource_id=schedule_id,
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
    