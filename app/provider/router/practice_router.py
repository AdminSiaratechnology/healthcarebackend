from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import ValidationError, BaseModel
from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.provider.practice import PracticeSchema
from beanie import PydanticObjectId
import json
import os
from app.provider.models.practice import Practice
from app.provider.models.providers import Provider
router = APIRouter(prefix="/provider", tags=["Providers"])

class PracticeCreateRequest(BaseModel):
    provider_id: str
    facility_ids: list[str] = []
    primary_facility_id: str | None = None
    practice: PracticeSchema


def _decrypt_json(client_encryption, value):
    if not value:
        return None
    raw = decrypt_value(client_encryption, value)
    if isinstance(raw, (bytes, bytearray)):
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return None
    if isinstance(raw, dict):
        return raw
    return None


@router.post("/practice")
async def create_practice(
    payload: PracticeCreateRequest,
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

        # Validate Provider
        try:
            prov_oid = PydanticObjectId(payload.provider_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid provider_id")
        provider = await Provider.get(prov_oid)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        # Authorization: admin/super_admin or owner of provider
        role_val = None
        if user.role is not None:
            try:
                r = decrypt_value(ce, user.role)
                role_val = r.decode("utf-8") if isinstance(r, (bytes, bytearray)) else r
            except Exception:
                role_val = None
        is_admin = role_val in {"admin", "super_admin"}
        if not is_admin and provider.user_id != str(user.id):
            raise HTTPException(status_code=403, detail="Forbidden")

        # Validate Facilities
        facilities: list[Facility] = []
        for fid in payload.facility_ids:
            try:
                foid = PydanticObjectId(fid)
            except Exception:
                raise HTTPException(status_code=400, detail=f"Invalid facility_id: {fid}")
            fac = await Facility.get(foid)
            if not fac:
                raise HTTPException(status_code=404, detail=f"Facility not found: {fid}")
            facilities.append(fac)

        primary_facility = None
        if payload.primary_facility_id:
            try:
                pfoid = PydanticObjectId(payload.primary_facility_id)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid primary_facility_id")
            primary_facility = await Facility.get(pfoid)
            if not primary_facility:
                raise HTTPException(status_code=404, detail="Primary facility not found")

        # Encrypt practice settings
        pr = payload.practice
        enc_assigned = encrypt_value(ce, dek_id, pr.assigned_practice.value) if pr.assigned_practice else None
        enc_rotation = encrypt_value(ce, dek_id, json.dumps(pr.rotation_days.model_dump())) if pr.rotation_days else None
        enc_oncall = encrypt_value(ce, dek_id, json.dumps(pr.on_call_days.model_dump())) if pr.on_call_days else None
        enc_visit = encrypt_value(ce, dek_id, pr.visit_type.value) if pr.visit_type else None
        enc_billing = encrypt_value(ce, dek_id, pr.billing_location_code.value) if pr.billing_location_code else None

        doc = Practice(
            provider_id=provider,
            facility_ids=facilities,
            primary_facility_id=primary_facility,
            assigned_practice=enc_assigned,
            rotation_days=enc_rotation,
            on_calls_days=enc_oncall,
            default_visit_type=enc_visit,
            billing_location_code=enc_billing,
        )
        await doc.insert()

        await log_audit(
            request=request,
            user_id=current_user_id,
            action="CREATE",
            resource="practice",
            resource_id=str(doc.id),
            status="success",
            notes="Practice created",
        )

        return {
            "id": str(doc.id),
        }
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="CREATE",
            resource="practice",
            resource_id="N/A",
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/practice/{provider_id}")
async def get_practice_by_provider(
    provider_id: str,
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

        try:
            prov_oid = PydanticObjectId(provider_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid provider_id")

        provider = await Provider.get(prov_oid)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        role_val = None
        if user.role is not None:
            try:
                r = decrypt_value(ce, user.role)
                role_val = r.decode("utf-8") if isinstance(r, (bytes, bytearray)) else r
            except Exception:
                role_val = None
        is_admin = role_val in {"admin", "super_admin"}
        if not is_admin and provider.user_id != str(user.id):
            raise HTTPException(status_code=403, detail="Forbidden")

        practice = await Practice.find_one(Practice.provider_id.id == provider.id)
        if not practice:
            raise HTTPException(status_code=404, detail="Practice not found")

        rotation = _decrypt_json(ce, practice.rotation_days) or {}
        oncall = _decrypt_json(ce, practice.on_calls_days) or {}
        visit_raw = decrypt_value(ce, practice.default_visit_type) if practice.default_visit_type else None
        if isinstance(visit_raw, (bytes, bytearray)):
            visit_raw = visit_raw.decode("utf-8")
        billing_raw = decrypt_value(ce, practice.billing_location_code) if practice.billing_location_code else None
        if isinstance(billing_raw, (bytes, bytearray)):
            billing_raw = billing_raw.decode("utf-8")
        assigned_raw = decrypt_value(ce, practice.assigned_practice) if practice.assigned_practice else None
        if isinstance(assigned_raw, (bytes, bytearray)):
            assigned_raw = assigned_raw.decode("utf-8")

        return {
            "id": str(practice.id),
            "provider_id": str(provider.id),
            "facility_ids": [str((await f.fetch()).id) for f in (practice.facility_ids or [])],
            "primary_facility_id": (str((await practice.primary_facility_id.fetch()).id) if practice.primary_facility_id else None),
            "assigned_practice": assigned_raw,
            "rotation_days": rotation,
            "on_call_days": oncall,
            "visit_type": visit_raw,
            "billing_location_code": billing_raw,
        }
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="READ",
            resource="practice",
            resource_id=provider_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))



# @router.put("/practice/{practice_id}")
# async def update_practice(
#     practice_id: str,
#     payload: PracticeSchema,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         client_encryption = getattr(request.app, "client_encryption", None)
#         if client_encryption is None:
#             client_encryption = init_encryption()
#         dek_id = getattr(request.app, "dek_id", None)   
#         if dek_id is None:
#             dek_id = ensure_data_key()
        
#         def enc_json_or_none(obj):
#             if obj is None:
#                 return None
            
#             if hasattr(obj, "model_dump"):
#                 data = obj.model_dump(mode="json")
#             elif hasattr(obj, "value"):
#                 data = obj.value
#             else:
#                 data = obj
                
#             return encrypt_value(
#                 client_encryption,
#                 dek_id,
#                 json.dumps(data)
#             )
#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")
#         practice_doc = await Practice.get(practice_id)
#         if not practice_doc:
#             raise HTTPException(status_code=404, detail="Practice not found")
#         practice_doc.assigned_practice = enc_json_or_none(payload.assigned_practice)
#         practice_doc.rotation_days = enc_json_or_none(payload.rotation_days)
#         practice_doc.on_calls_days = enc_json_or_none(payload.on_call_days)
#         practice_doc.default_visit_type = enc_json_or_none(payload.visit_type)
#         practice_doc.billing_location_code = enc_json_or_none(payload.billing_location_code)

#         if payload.provider_id:
#             try:
#                 prov_oid = PydanticObjectId(payload.provider_id)
#             except Exception:
#                  raise HTTPException(status_code=400, detail="Invalid provider_id format")
            
#             provider = await Provider.get(prov_oid)
#             if not provider:
#                 raise HTTPException(status_code=404, detail="Provider not found")
#             practice_doc.provider_id = provider

#         if payload.facility_ids is not None:
#             facilities = []
#             for fid in payload.facility_ids:
#                 try:
#                     foid = PydanticObjectId(fid)
#                 except Exception:
#                      raise HTTPException(status_code=400, detail=f"Invalid facility_id format: {fid}")
                
#                 fac = await Facility.get(foid)
#                 if not fac:
#                     raise HTTPException(status_code=404, detail=f"Facility {fid} not found")
#                 facilities.append(fac)
#             practice_doc.facility_ids = facilities

#         if payload.primary_facility_id:
#             try:
#                 pfoid = PydanticObjectId(payload.primary_facility_id)
#             except Exception:
#                 raise HTTPException(status_code=400, detail="Invalid primary_facility_id format")
            
#             p_fac = await Facility.get(pfoid)
#             if not p_fac:
#                 raise HTTPException(status_code=404, detail="Primary Facility not found")
#             practice_doc.primary_facility_id = p_fac

#         practice_doc.updated_at = datetime.now(timezone.utc)
#         await practice_doc.save()
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Update",
#                 resource="Practice",
#                 resource_id=str(practice_doc.id),
#                 status="success",
#                 notes="Practice updated successfully",
#             )
#         except Exception:
#             pass
#         return {"success": True, "id": str(practice_doc.id)}
#     except HTTPException:
#         raise
#     except Exception as e:
#         await log_audit(
#             request=request,
#             user_id=current_user_id,
#             action="Update",
#             resource="Practice",
#             resource_id=practice_id,
#             status="failed",
#             notes=str(e),
#         )
#         raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@router.put("/practice/{practice_id}")
async def update_practice(
    practice_id: str,
    payload: PracticeSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # ---------- Encryption setup ----------
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        # ---------- Helper: same as POST behavior ----------
        def encrypt_field(value):
            if value is None:
                return None

            # Enum → direct value
            if hasattr(value, "value"):
                return encrypt_value(ce, dek_id, value.value)

            # Pydantic model → dict → json
            if hasattr(value, "model_dump"):
                return encrypt_value(
                    ce,
                    dek_id,
                    json.dumps(value.model_dump(mode="json"))
                )

            # Dict → json
            if isinstance(value, dict):
                return encrypt_value(
                    ce,
                    dek_id,
                    json.dumps(value)
                )

            # Plain string / fallback
            return encrypt_value(ce, dek_id, str(value))

        # ---------- User validation ----------
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # ---------- Practice validation ----------
        practice_doc = await Practice.get(practice_id)
        if not practice_doc:
            raise HTTPException(status_code=404, detail="Practice not found")

        # ---------- Update encrypted fields ----------
        practice_doc.assigned_practice = encrypt_field(payload.assigned_practice)
        practice_doc.rotation_days = encrypt_field(payload.rotation_days)
        practice_doc.on_calls_days = encrypt_field(payload.on_call_days)
        practice_doc.default_visit_type = encrypt_field(payload.visit_type)
        practice_doc.billing_location_code = encrypt_field(payload.billing_location_code)

        # ---------- Provider update ----------
        if payload.provider_id:
            try:
                prov_oid = PydanticObjectId(payload.provider_id)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid provider_id")

            provider = await Provider.get(prov_oid)
            if not provider:
                raise HTTPException(status_code=404, detail="Provider not found")

            practice_doc.provider_id = provider

        # ---------- Facilities update ----------
        if payload.facility_ids is not None:
            facilities = []
            for fid in payload.facility_ids:
                try:
                    foid = PydanticObjectId(fid)
                except Exception:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid facility_id: {fid}"
                    )

                fac = await Facility.get(foid)
                if not fac:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Facility not found: {fid}"
                    )
                facilities.append(fac)

            practice_doc.facility_ids = facilities

        # ---------- Primary facility ----------
        if payload.primary_facility_id:
            try:
                pfoid = PydanticObjectId(payload.primary_facility_id)
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid primary_facility_id"
                )

            primary_fac = await Facility.get(pfoid)
            if not primary_fac:
                raise HTTPException(
                    status_code=404,
                    detail="Primary facility not found"
                )

            practice_doc.primary_facility_id = primary_fac

        # ---------- Save ----------
        practice_doc.updated_at = datetime.now(timezone.utc)
        await practice_doc.save()

        # ---------- Audit ----------
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="UPDATE",
            resource="practice",
            resource_id=str(practice_doc.id),
            status="success",
            notes="Practice updated successfully",
        )

        return {
            "success": True,
            "id": str(practice_doc.id),
        }

    except HTTPException:
        raise

    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="UPDATE",
            resource="practice",
            resource_id=practice_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error"
        )
