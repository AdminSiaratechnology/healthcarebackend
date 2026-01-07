from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.patients.medical import PatientMedicalSchema
from beanie import PydanticObjectId
import json
import os
from app.patients.models.patients import PatientDoc
from app.patients.models.medical import PatientMedicalDoc

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


@router.post("/medical/create/{patient_id}/")
async def create_patient_medical(
    patient_id: str,
    payload: PatientMedicalSchema,
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

        diag_json = (
            json.dumps(payload.diagonisis_information.model_dump(mode="json", serialize_as_any=True))
            if getattr(payload, "diagonisis_information", None) else None
        )
        allergies_val = getattr(payload, "allergies", None)
        allergies_json = (
            json.dumps(allergies_val.model_dump(mode="json", serialize_as_any=True))
            if allergies_val else None
        )

        enc_diag = encrypt_value(ce, dek_id, diag_json) if diag_json is not None else None
        enc_allergies = encrypt_value(ce, dek_id, allergies_json) if allergies_json is not None else None

        doc = PatientMedicalDoc(
            patient_id=patient,
            diagonisis_information=enc_diag,
            allergies=enc_allergies,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await doc.insert()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Create",
            resource="Patient Medical",
            resource_id=str(doc.id),
            status="success",
            notes="Patient medical saved",
        )

        return {"id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Create",
            resource="Patient Medical",
            resource_id="N/A",
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/medical/get/{patient_id}/")
async def get_patient_medical(
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

        by_link = await PatientMedicalDoc.find(PatientMedicalDoc.patient_id.id == patient.id).to_list()
        by_str = await PatientMedicalDoc.find(PatientMedicalDoc.patient_id == str(patient.id)).to_list()

        seen = set()
        docs = []
        for d in by_link + by_str:
            if str(d.id) in seen:
                continue
            seen.add(str(d.id))
            docs.append(d)

        result = [
            {
                "id": str(m.id),
                "diagonisis_information": _decrypt_json_field(ce, m.diagonisis_information),
                "allergies": _decrypt_json_field(ce, m.allergies),
                "created_at": m.created_at,
                "updated_at": m.updated_at,
            } for m in docs
        ]

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Patient Medical",
            resource_id=str(patient.id),
            status="success",
            notes="Patient medical fetched",
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Read",
            resource="Patient Medical",
            resource_id=patient_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))



@router.put("/medical/update/{medical_id}/")
async def update_patient_medical(
    medical_id: str,
    payload: PatientMedicalSchema,
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
            m_oid = PydanticObjectId(medical_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Medical ID format")
        insurance = await PatientMedicalDoc.get(m_oid)
        if not insurance:
            raise HTTPException(status_code=404, detail="Patient Medical not found")

        diag_json = (
            json.dumps(payload.diagonisis_information.model_dump(mode="json", serialize_as_any=True))
            if getattr(payload, "diagonisis_information", None) else None
        )
        allergies_val = getattr(payload, "allergies", None)
        allergies_json = (
            json.dumps(allergies_val.model_dump(mode="json", serialize_as_any=True))
            if allergies_val else None
        )

        if diag_json is not None:
            insurance.diagonisis_information = encrypt_value(ce, dek_id, diag_json)
        if allergies_json is not None:
            insurance.allergies = encrypt_value(ce, dek_id, allergies_json)

        insurance.updated_at = datetime.now(timezone.utc)
        await insurance.save()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Update",
            resource="Patient Medical",
            resource_id=str(insurance.id),
            status="success",
            notes="Patient medical updated",
        )

        return {"id": str(insurance.id)}
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Update",
            resource="Patient Medical",
            resource_id=medical_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))