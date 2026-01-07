from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.patients.emergency_contact import PatientEmergencyContact
from beanie import PydanticObjectId
import json
import os
from app.patients.models.patients import PatientDoc
from app.patients.models.emergency_contact import PatientEmergencyContactDoc

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


@router.post("/emergency-contact/create/{patient_id}/")
async def create_patient_emergency_contact(
    patient_id: str,
    payload: PatientEmergencyContact,
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

        primary_json = json.dumps(payload.emergency_contact.model_dump()) if payload.emergency_contact else None
        secondary_json = json.dumps(payload.secondary_contact.model_dump()) if payload.secondary_contact else None

        enc_primary = encrypt_value(ce, dek_id, primary_json) if primary_json is not None else None
        enc_secondary = encrypt_value(ce, dek_id, secondary_json) if secondary_json is not None else None

        doc = PatientEmergencyContactDoc(
            patient_id=patient,
            emergency_contact=enc_primary,
            secondary_contact=enc_secondary,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await doc.insert()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Create",
            resource="Patient Emergency Contact",
            resource_id=str(doc.id),
            status="success",
            notes="Patient emergency contact saved",
        )

        return {"id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Create",
            resource="Patient Emergency Contact",
            resource_id="N/A",
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emergency-contact/get/{patient_id}/")
async def get_patient_emergency_contacts(
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

        by_link = await PatientEmergencyContactDoc.find(PatientEmergencyContactDoc.patient_id.id == patient.id).to_list()
        by_str = await PatientEmergencyContactDoc.find(PatientEmergencyContactDoc.patient_id == str(patient.id)).to_list()

        seen = set()
        docs = []
        for d in by_link + by_str:
            if str(d.id) in seen:
                continue
            seen.add(str(d.id))
            docs.append(d)

        result = [
            {
                "id": str(ec.id),
                "emergency_contact": _decrypt_json_field(ce, ec.emergency_contact),
                "secondary_contact": _decrypt_json_field(ce, ec.secondary_contact),
                "created_at": ec.created_at,
                "updated_at": ec.updated_at,
            } for ec in docs
        ]

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Patient Emergency Contact",
            resource_id=str(patient.id),
            status="success",
            notes="Patient emergency contacts fetched",
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Read",
            resource="Patient Emergency Contact",
            resource_id=patient_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))
    



@router.put("/emergency-contact/update/{contact_id}/")
async def update_patient_emergency_contact(
    contact_id: str,
    payload: PatientEmergencyContact,
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
            ec_oid = PydanticObjectId(contact_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Emergency Contact ID format")
        emergency_contact = await PatientEmergencyContactDoc.get(ec_oid)
        if not emergency_contact:
            raise HTTPException(status_code=404, detail="Patient Emergency Contact not found")

        primary_json = json.dumps(payload.emergency_contact.model_dump()) if payload.emergency_contact else None
        secondary_json = json.dumps(payload.secondary_contact.model_dump()) if payload.secondary_contact else None

        if primary_json is not None:
            emergency_contact.emergency_contact = encrypt_value(ce, dek_id, primary_json)
        if secondary_json is not None:
            emergency_contact.secondary_contact = encrypt_value(ce, dek_id, secondary_json)

        emergency_contact.updated_at = datetime.now(timezone.utc)
        await emergency_contact.save()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Update",
            resource="Patient Emergency Contact",
            resource_id=str(emergency_contact.id),
            status="success",
            notes="Patient emergency contact updated",
        )

        return {"id": str(emergency_contact.id)}
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Update",
            resource="Patient Emergency Contact",
            resource_id=contact_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))
