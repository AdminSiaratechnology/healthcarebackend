from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.patients.insurance import InsuranceSchema
from beanie import PydanticObjectId
import json
import os
from app.patients.models.patients import PatientDoc
from app.patients.models.insurance import PatientInsuranceDoc

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


@router.post("/insurance/create/{patient_id}/")
async def create_patient_insurance(
    patient_id: str,
    payload: InsuranceSchema,
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

        med_info_json = json.dumps(payload.medicare_information.model_dump()) if payload.medicare_information else None
        med_adv_json = json.dumps(payload.medicare_advantage.model_dump()) if payload.medicare_advantage else None
        # primary_secondary_insurance exists in model; schema may omit. If provided via extended schema, handle later.

        enc_med_info = encrypt_value(ce, dek_id, med_info_json) if med_info_json is not None else None
        enc_med_adv = encrypt_value(ce, dek_id, med_adv_json) if med_adv_json is not None else None

        doc = PatientInsuranceDoc(
            patient_id=patient,
            medicare_information=enc_med_info,
            medicare_advantage=enc_med_adv,
            primary_secondary_insurance=None,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await doc.insert()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Create",
            resource="Patient Insurance",
            resource_id=str(doc.id),
            status="success",
            notes="Patient insurance saved",
        )

        return {"id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Create",
            resource="Patient Insurance",
            resource_id="N/A",
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/insurance/get/{patient_id}/")
async def get_patient_insurance(
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

         # ---------------- Insurance (Patient + created_by) ----------------

        insurance = await PatientInsuranceDoc.find(
            PatientInsuranceDoc.patient_id.id == patient.id,
            PatientInsuranceDoc.created_by.id == user.id
        ).sort("created_at").to_list()
       
        

        result = [
            {
                "id": str(ins.id),
                "medicare_information": _decrypt_json_field(ce, ins.medicare_information),
                "medicare_advantage": _decrypt_json_field(ce, ins.medicare_advantage),
                "primary_secondary_insurance": _decrypt_json_field(ce, ins.primary_secondary_insurance),
                "created_at": ins.created_at,
                "updated_at": ins.updated_at,
            } for ins in insurance
        ]

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Patient Insurance",
            resource_id=str(patient.id),
            status="success",
            notes="Patient insurance fetched",
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Read",
            resource="Patient Insurance",
            resource_id=patient_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))
    


@router.put("/insurance/update/{insurance_id}/")
async def update_patient_insurance(
    insurance_id: str,
    payload: InsuranceSchema,
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
            ins_oid = PydanticObjectId(insurance_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Insurance ID format")
        insurance = await PatientInsuranceDoc.get(ins_oid)
        if not insurance:
            raise HTTPException(status_code=404, detail="Patient Insurance not found")

        med_info_json = json.dumps(payload.medicare_information.model_dump()) if payload.medicare_information else None
        med_adv_json = json.dumps(payload.medicare_advantage.model_dump()) if payload.medicare_advantage else None
        primary_sec_json = json.dumps(payload.primary_secondary_insurance.model_dump()) if payload.primary_secondary_insurance else None

        if med_info_json is not None:
            insurance.medicare_information = encrypt_value(ce, dek_id, med_info_json)
        if med_adv_json is not None:
            insurance.medicare_advantage = encrypt_value(ce, dek_id, med_adv_json)
        if primary_sec_json is not None:
            insurance.primary_secondary_insurance = encrypt_value(ce, dek_id, primary_sec_json)


        insurance.updated_at = datetime.now(timezone.utc)
        await insurance.save()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Update",
            resource="Patient Insurance",
            resource_id=str(insurance.id),
            status="success",
            notes="Patient insurance updated",
        )

        return {"id": str(insurance.id)}
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Update",
            resource="Patient Insurance",
            resource_id=insurance_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))
