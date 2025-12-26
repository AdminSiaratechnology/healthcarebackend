from datetime import datetime, timezone, date
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key, encrypt_value_deterministic
from app.accounts.models.user import UserRole
from app.utils.audit import log_audit
from app.schemas.prescription.prescription import PrescriptionSchema
from beanie import PydanticObjectId
import json
import os

from app.prescriptions.models.prescription import PrescriptionDoc
from app.patients.models.patients import PatientDoc

router = APIRouter(prefix="/prescription", tags=["Prescription"])


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


@router.post("/create/{patient_id}/")
async def create_prescription(
    patient_id: str,
    payload: PrescriptionSchema,
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

        enc_medication = encrypt_value(ce, dek_id, payload.medication) if payload.medication else None
        enc_dosage = encrypt_value(ce, dek_id, payload.dosage) if payload.dosage else None
        enc_frequency = encrypt_value(ce, dek_id, payload.frequency.value) if payload.frequency else None
        enc_route = encrypt_value(ce, dek_id, payload.route.value) if payload.route else None
        enc_quantity = encrypt_value(ce, dek_id, payload.quantity) if payload.quantity is not None else None
        enc_refills = encrypt_value(ce, dek_id, payload.refills) if payload.refills is not None else None
        enc_instructions = encrypt_value(ce, dek_id, payload.instructions) if payload.instructions else None

        doc = PrescriptionDoc(
            patient_id=patient,
            medication=enc_medication,
            dosage=enc_dosage,
            frequency=enc_frequency,
            route=enc_route,
            quantity=enc_quantity,
            refills=enc_refills,
            instructions=enc_instructions,
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
                resource="Prescription",
                resource_id=str(doc.id),
                status="success",
                notes="Prescription created",
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
                resource="Prescription",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get/{patient_id}/")
async def get_prescriptions(
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

        by_link = await PrescriptionDoc.find(PrescriptionDoc.patient_id.id == patient.id).to_list()
        by_str = await PrescriptionDoc.find(PrescriptionDoc.patient_id == str(patient.id)).to_list()

        seen = set()
        docs = []
        for d in by_link + by_str:
            if str(d.id) in seen:
                continue
            seen.add(str(d.id))
            docs.append(d)

        result = []
        for p in docs:
            result.append({
                "id": str(p.id),
                "patient_id": str(p.patient_id.ref.id),
                # "patient_id": str(getattr(getattr(p, "patient_id", None), "id", getattr(p, "patient_id", ""))),
                "medication": _decrypt_value(ce, p.medication),
                "dosage": _decrypt_value(ce, p.dosage),
                "frequency": _decrypt_value(ce, p.frequency),
                "route": _decrypt_value(ce, p.route),
                "quantity": _decrypt_value(ce, p.quantity),
                "refills": _decrypt_value(ce, p.refills),
                "instructions": _decrypt_value(ce, p.instructions),
                "created_at": p.created_at,
                "updated_at": p.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Prescription",
                resource_id=str(patient.id),
                status="success",
                notes="Prescriptions fetched",
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
                resource="Prescription",
                resource_id=patient_id,
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
