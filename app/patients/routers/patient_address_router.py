from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.patients.addressinfo import PatientAddressSchema
from beanie import PydanticObjectId
import json
import os
from app.patients.models.patients import PatientDoc
from app.patients.models.addressinfo import PatientAddressInfoDoc

router = APIRouter(prefix="/patient", tags=["Patients"])


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


@router.post("/address/create/{patient_id}/")
async def create_patient_address(
    patient_id: str,
    payload: PatientAddressSchema,
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
            p_oid = PydanticObjectId(patient_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Patient ID format")
        patient = await PatientDoc.get(p_oid)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        cur_json = json.dumps(payload.current_address.model_dump()) if payload.current_address else None
        prev_json = json.dumps(payload.previous_address.model_dump()) if payload.previous_address else None

        enc_current = encrypt_value(ce, dek_id, cur_json) if cur_json is not None else None
        enc_previous = encrypt_value(ce, dek_id, prev_json) if prev_json is not None else None

        doc = PatientAddressInfoDoc(
            patient_id=patient,
            current_address=enc_current,
            previous_address=enc_previous,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await doc.insert()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Create",
            resource="Patient Address",
            resource_id=str(doc.id),
            status="success",
            notes="Patient address saved",
        )

        return {"id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Create",
            resource="Patient Address",
            resource_id="N/A",
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/address/get/{patient_id}/")
async def get_patient_addresses(
    patient_id: str,
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
            p_oid = PydanticObjectId(patient_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Patient ID format")
        patient = await PatientDoc.get(p_oid)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        by_link = await PatientAddressInfoDoc.find(PatientAddressInfoDoc.patient_id.id == patient.id).to_list()
        by_str = await PatientAddressInfoDoc.find(PatientAddressInfoDoc.patient_id == str(patient.id)).to_list()

        seen = set()
        docs = []
        for d in by_link + by_str:
            if str(d.id) in seen:
                continue
            seen.add(str(d.id))
            docs.append(d)

        result = [
            {
                "id": str(a.id),
                "current_address": _decrypt_json_field(ce, a.current_address),
                "previous_address": _decrypt_json_field(ce, a.previous_address),
                "created_at": a.created_at,
                "updated_at": a.updated_at,
            } for a in docs
        ]

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Patient Address",
            resource_id=str(patient.id),
            status="success",
            notes="Patient addresses fetched",
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Read",
            resource="Patient Address",
            resource_id=patient_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))
    


@router.put("/address/update/{address_id}/")
async def update_patient_address(
    address_id: str,
    payload: PatientAddressSchema,
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
            addr_oid = PydanticObjectId(address_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Address ID format")
        address_doc = await PatientAddressInfoDoc.get(addr_oid)
        if not address_doc:
            raise HTTPException(status_code=404, detail="Patient Address not found")

        cur_json = json.dumps(payload.current_address.model_dump()) if payload.current_address else None
        prev_json = json.dumps(payload.previous_address.model_dump()) if payload.previous_address else None

        if cur_json is not None:
            address_doc.current_address = encrypt_value(ce, dek_id, cur_json)
        if prev_json is not None:
            address_doc.previous_address = encrypt_value(ce, dek_id, prev_json)

        address_doc.updated_at = datetime.now(timezone.utc)
        await address_doc.save()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Update",
            resource="Patient Address",
            resource_id=str(address_doc.id),
            status="success",
            notes="Patient address updated",
        )

        return {"id": str(address_doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Update",
            resource="Patient Address",
            resource_id=address_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e)) 
