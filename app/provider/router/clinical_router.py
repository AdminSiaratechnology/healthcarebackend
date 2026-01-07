from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import ValidationError, BaseModel
from app.accounts.models import provider
from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.provider.clinical import ClinicalDataSchema
from beanie import PydanticObjectId
import json
import os
from app.provider.models.clinical import clinical
from app.provider.models.providers import Provider


router = APIRouter(prefix="/provider", tags=["Providers"])

class ClinicalCreateRequest(BaseModel):
    provider_id: str
    clinical: ClinicalDataSchema

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
    if isinstance(raw, dict) or isinstance(raw, list):
        return raw
    return None

@router.post("/clinical")
async def create_clinical(
    payload: ClinicalCreateRequest,
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

        try:
            prov_oid = PydanticObjectId(payload.provider_id)
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

        cl = payload.clinical
        dnt = None
        try:
            v = getattr(cl.default_note_template, "value", cl.default_note_template)
            dnt = encrypt_value(ce, dek_id, v) if v else None
        except Exception:
            dnt = None
        meds = encrypt_value(ce, dek_id, json.dumps([m.model_dump() for m in (cl.medications or [])])) if getattr(cl, "medications", None) else None
        labs = encrypt_value(ce, dek_id, json.dumps([l.model_dump() for l in (cl.lab_tests or [])])) if getattr(cl, "lab_tests", None) else None
        orders = encrypt_value(ce, dek_id, json.dumps([o.model_dump() for o in (cl.orders or [])])) if getattr(cl, "orders", None) else None
        stmt = encrypt_value(ce, dek_id, cl.statement) if getattr(cl, "statement", None) else None
        wf_enc = encrypt_value(ce, dek_id, json.dumps(cl.work_flow_automation.model_dump())) if getattr(cl, "work_flow_automation", None) else None

        doc = clinical(
            provider_id=provider,
            default_note_template=dnt,
            medications=meds,
            lab_tests=labs,
            orders=orders,
            statement=stmt,
            work_flow_automation=wf_enc,
            created_by=user,
        )
        await doc.insert()

        await log_audit(
            request=request,
            user_id=current_user_id,
            action="CREATE",
            resource="clinical",
            resource_id=str(doc.id),
            status="success",
            notes="Clinical created",
        )

        return {"id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="CREATE",
            resource="clinical",
            resource_id="N/A",
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/clinical/{provider_id}")
async def get_clinical(
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

        doc = await clinical.find_one(clinical.provider_id.id == provider.id)
        if not doc:
            raise HTTPException(status_code=404, detail="Clinical not found")

        dnt_raw = decrypt_value(ce, doc.default_note_template) if doc.default_note_template else None
        if isinstance(dnt_raw, (bytes, bytearray)):
            dnt_raw = dnt_raw.decode("utf-8")
        meds = _decrypt_json(ce, doc.medications) or []
        labs = _decrypt_json(ce, doc.lab_tests) or []
        ords = _decrypt_json(ce, doc.orders) or []
        stmt_raw = decrypt_value(ce, doc.statement) if doc.statement else None
        if isinstance(stmt_raw, (bytes, bytearray)):
            stmt_raw = stmt_raw.decode("utf-8")
        wf = _decrypt_json(ce, doc.work_flow_automation) or None

        return {
            "id": str(doc.id),
            "provider_id": str(provider.id),
            "default_note_template": dnt_raw,
            "medications": meds,
            "lab_tests": labs,
            "orders": ords,
            "statement": stmt_raw,
            "work_flow_automation": wf,
        }
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="READ",
            resource="clinical",
            resource_id=provider_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))



@router.put("/clinical/{clinical_id}")
async def update_clinical(
    clinical_id: str,
    payload: ClinicalDataSchema,
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
        def enc_json_or_none(obj):
            if obj is None:
                return None
            try:
                return encrypt_value(ce, dek_id, json.dumps(obj.model_dump(mode="json")))
            except Exception:
                return encrypt_value(ce, dek_id, json.dumps(obj)) if isinstance(obj, dict) else encrypt_value(ce, dek_id, str(obj))
        def enc_list(objs):
            return encrypt_value(ce, dek_id, json.dumps([o.model_dump(mode="json") if hasattr(o, "model_dump") else o for o in (objs or [])])) if objs is not None else None
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        clinical_doc = await clinical.get(clinical_id)
        if not clinical_doc:
            raise HTTPException(status_code=404, detail="Clinical not found")
        clinical_doc.default_note_template = encrypt_value(ce, dek_id, getattr(payload.default_note_template, "value", payload.default_note_template)) if getattr(payload, "default_note_template", None) else None
        clinical_doc.medications = enc_list(payload.medications)
        clinical_doc.lab_tests = enc_list(payload.lab_tests)
        clinical_doc.orders = enc_list(payload.orders)
        clinical_doc.statement = encrypt_value(ce, dek_id, payload.statement) if getattr(payload    , "statement", None) else None
        clinical_doc.work_flow_automation = enc_json_or_none(payload.work_flow_automation)   
        await clinical_doc.save()
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="UPDATE",
                resource="clinical",
                resource_id=str(clinical_doc.id),
                status="success",
                notes="Clinical updated",
            )
        except Exception:
            pass
        return {"id": str(clinical_doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="UPDATE",
                resource="clinical",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
