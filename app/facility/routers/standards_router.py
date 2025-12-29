from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.standards import FacilityStandardsSchema
from beanie import PydanticObjectId

import json
import os
from app.facility.models.standards import StandardsDoc

router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/standards/{facility_id}/")
async def create_standards(
    facility_id: str,
    standards: FacilityStandardsSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        client_encryption = getattr(request.app, "client_encryption", None)
        if client_encryption is None:
            client_encryption = init_encryption()
        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()

        def enc_json_or_none(obj):
            return (
                encrypt_value(
                    client_encryption,
                    dek_id,
                    json.dumps(obj.model_dump(mode="json"))
                ) if obj is not None else None
            )

        try:
            facility_obj_id = PydanticObjectId(facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")

        facility = await Facility.get(facility_obj_id)
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        doc = StandardsDoc(
            facility_id=facility,
            diagnosis_coding=enc_json_or_none(standards.diagnosis_coding),
            procedure_coding=enc_json_or_none(standards.procedure_coding),
            laboratory_coding=enc_json_or_none(standards.laboratory_coding),
            allergy_coding=enc_json_or_none(standards.allergy_coding),
            terminology_update=enc_json_or_none(standards.terminology_update),
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
                resource="Standards",
                resource_id=str(doc.id),
                status="success",
                notes="Facility standards created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "standards_id": str(doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Create",
                resource="Standards",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while creating standards")


def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return json.loads(decrypted_raw)


@router.get("/get/standards/{facility_id}/")
async def get_standards(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    facility_obj = None
    try:
        facility_obj_id = PydanticObjectId(facility_id)
        facility_obj = await Facility.get(facility_obj_id)
    except Exception:
        pass

    if facility_obj is None:
        facility_obj = await Facility.get(facility_id)
    if not facility_obj:
        raise HTTPException(status_code=404, detail="Facility not found")

     # ---------------- ENCRYPTION ----------------
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    # ---------------- STANDARD  ----------------
    standard = await StandardsDoc.find(
        StandardsDoc.facility_id.id == facility_obj.id,
        StandardsDoc.created_by.id == user.id
    ).sort("-created_at").to_list()


    # ---------------- RESPONSE ----------------



    result = [
        {
            "id": str(sd.id),
            "diagnosis_coding": _decrypt_json_field(ce, sd.diagnosis_coding),
            "procedure_coding": _decrypt_json_field(ce, sd.procedure_coding),
            "laboratory_coding": _decrypt_json_field(ce, sd.laboratory_coding),
            "allergy_coding": _decrypt_json_field(ce, sd.allergy_coding),
            "terminology_update": _decrypt_json_field(ce, sd.terminology_update),
            "created_at": sd.created_at,
            "updated_at": sd.updated_at,
        } for sd in standard
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Standards",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Facility standards fetched successfully",
        )
    except Exception:
        pass

    return result
