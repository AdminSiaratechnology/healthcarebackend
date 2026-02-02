from datetime import datetime, timezone, date
from fastapi import APIRouter, Request, HTTPException, Depends, Query
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
from beanie.operators import In
import json
import os
from app.schedule.models.schedule import SchedulerDoc

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





@router.get("/list/")
async def list_schedules(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    from_date: date | None = Query(None, description="Filter start date (YYYY-MM-DD)"),
    to_date: date | None = Query(None, description="Filter end date (YYYY-MM-DD)"),
    facility_id: str | None = Query(None, description="Filter by single facility id"),
    provider_id: str | None = Query(None, description="Filter by single provider id"),
    facility_ids: list[str] | None = Query(None, description="Filter by multiple facility ids"),
    provider_ids: list[str] | None = Query(None, description="Filter by multiple provider ids"),
    department: str | None = Query(None, description="Filter by department"),
    search: str | None = Query(None, description="Search by facility/provider name"),
    patient_name: str | None = Query(None, description="Search schedules with patients by name (provider-linked)")
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        filters = [SchedulerDoc.created_by.id == user.id]
        fac_oids: list[PydanticObjectId] = []
        prov_oids: list[PydanticObjectId] = []
        if facility_id is not None:
            try:
                fac_oids.append(PydanticObjectId(facility_id))
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid facility_id")
        if facility_ids:
            for fid in facility_ids:
                try:
                    fac_oids.append(PydanticObjectId(fid))
                except Exception:
                    raise HTTPException(status_code=400, detail=f"Invalid facility_id in list: {fid}")
        if fac_oids:
            filters.append(In(SchedulerDoc.facility_id.id, fac_oids))

        if provider_id is not None:
            try:
                prov_oids.append(PydanticObjectId(provider_id))
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid provider_id")
        if provider_ids:
            for pid in provider_ids:
                try:
                    prov_oids.append(PydanticObjectId(pid))
                except Exception:
                    raise HTTPException(status_code=400, detail=f"Invalid provider_id in list: {pid}")
        if prov_oids:
            filters.append(In(SchedulerDoc.provider_id.id, prov_oids))

        scheds = await SchedulerDoc.find(*filters).sort("-created_at").to_list()

        
        items = []
        for s in scheds:
            try:
                await s.fetch_links()
            except Exception:
                pass
            shift = _decrypt_json_field(ce, s.shift_time)
            facility_name = None
            fac_id_str = None
            try:
                fac_id_str = str(getattr(getattr(s.facility_id, "ref", None), "id", "")) or None
            except Exception:
                fac_id_str = None
            if fac_id_str:
                fac_obj = None
                try:
                    fac_obj = await Facility.get(PydanticObjectId(fac_id_str))
                except Exception:
                    try:
                        fac_obj = await Facility.get(fac_id_str)
                    except Exception:
                        fac_obj = None
                if fac_obj and getattr(fac_obj, "basic", None):
                    fac_payload = _decrypt_json_field(ce, fac_obj.basic)
                    bi = (fac_payload or {}).get("basic_info") or {}
                    facility_name = bi.get("facility_name")
            provider_full_name = None
            prov_id_str = None
            try:
                prov_id_str = str(getattr(getattr(s.provider_id, "ref", None), "id", "")) or None
            except Exception:
                prov_id_str = None
            if prov_id_str:
                prov_obj = None
                try:
                    prov_obj = await Provider.get(PydanticObjectId(prov_id_str))
                except Exception:
                    try:
                        prov_obj = await Provider.get(prov_id_str)
                    except Exception:
                        prov_obj = None
                if prov_obj:
                    try:
                        await prov_obj.fetch_links()
                    except Exception:
                        pass
                    u = getattr(prov_obj, "user", None)
                    if u and getattr(u, "full_name", None):
                        provider_full_name = _decrypt_value(ce, u.full_name)
                    else:
                        uid = getattr(prov_obj, "user_id", None)
                        if uid:
                            # try both as ObjectId and plain string
                            usr_doc = None
                            try:
                                usr_doc = await UserDoc.get(PydanticObjectId(uid))
                            except Exception:
                                try:
                                    usr_doc = await UserDoc.get(uid)
                                except Exception:
                                    usr_doc = None
                            if usr_doc and getattr(usr_doc, "full_name", None):
                                provider_full_name = _decrypt_value(ce, usr_doc.full_name)
            patient_names_blob = ""
            patients_list = []
            try:
                pid_for_pat = None
                try:
                    pid_for_pat = PydanticObjectId(prov_id_str) if prov_id_str else None
                except Exception:
                    pid_for_pat = None
                if pid_for_pat:
                    from app.patients.models.patients import PatientDoc
                    patients_list = await PatientDoc.find(
                        PatientDoc.provider_id.id == pid_for_pat,
                        PatientDoc.created_by.id == user.id
                    ).to_list()
                    names = []
                    for pdoc in patients_list:
                        try:
                            ulink = getattr(pdoc, "user_id", None)
                            if ulink:
                                udoc = await ulink.fetch()
                                nm = _decrypt_value(ce, getattr(udoc, "full_name", None))
                                if nm:
                                    names.append(str(nm))
                        except Exception:
                            pass
                    patient_names_blob = " ".join(names).lower()
            except Exception:
                patient_names_blob = ""
            # search by facility/provider name (case-insensitive)
            if search:
                blob = " ".join([
                    str(facility_name or ""),
                    str(provider_full_name or ""),
                    str(patient_names_blob or ""),
                ]).lower()
                if not all(t in blob for t in (search or "").lower().split()):
                    continue

            # optional patient name search by provider linkage
            if patient_name:
                q_tokens = [t for t in (patient_name or "").lower().split() if t]
                if not all(t in (patient_names_blob or "") for t in q_tokens):
                    continue
            # In-memory filters: date range and department
            sel_date_str = _decrypt_value(ce, s.selected_date)
            sel_date_obj = None
            try:
                if sel_date_str:
                    sel_date_obj = date.fromisoformat(str(sel_date_str))
            except Exception:
                sel_date_obj = None

            if from_date and to_date:
                if not sel_date_obj or not (from_date <= sel_date_obj <= to_date):
                    continue
            elif from_date and not to_date:
                if not sel_date_obj or sel_date_obj != from_date:
                    continue
            elif to_date and not from_date:
                if not sel_date_obj or sel_date_obj != to_date:
                    continue

            if department:
                dept_val = _decrypt_value(ce, s.department)
                if str(department).strip().lower() not in str(dept_val or "").strip().lower():
                    continue
            
            patient_count = len(patients_list) if patients_list else 0

            items.append({
                "id": str(s.id),
                "facility_id": str(s.facility_id.ref.id),
                "provider_id": str(s.provider_id.ref.id),
                "facility_name": facility_name,
                "provider_full_name": provider_full_name,
                "selected_date": sel_date_str,
                "shift_time": shift,
                "patient_count": patient_count,
                "department": _decrypt_value(ce, s.department),
                "is_create_recurring_shift": _decrypt_value(ce, s.is_create_recurring_shift),
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Scheduler",
                resource_id="N/A",
                status="success",
                notes="Schedules listed",
            )
        except Exception:
            pass

        return {"items": items}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Read",
                resource="Scheduler",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e)) 
