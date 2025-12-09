from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.quality import QualitySchema
from beanie import PydanticObjectId
import json
import os
from app.facility.models.quality import QualityDoc

router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/quality/{facility_id}/")
async def create_quality(
    facility_id: str,
    quality: QualitySchema,
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

        def enc_or_none(val):
            return encrypt_value(client_encryption, dek_id, val) if val is not None else None

        def enc_json_or_none(obj):
            return (
                encrypt_value(client_encryption, dek_id, json.dumps(obj.model_dump()))
                if obj is not None else None
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

        quality_doc = QualityDoc(
            facility_id=facility,
            enable_mds_reporting=enc_or_none(quality.enable_mds_reporting),
            enable_quality_measure=enc_or_none(quality.enable_quality_measure),
            enable_infection_control_tracking=enc_or_none(quality.enable_infection_control_tracking),
            fall_risk_program=enc_or_none(quality.fall_risk_program),
            quality_reporting=enc_json_or_none(quality.quality_reporting),
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await quality_doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Quality",
                resource_id=str(quality_doc.id),
                status="success",
                notes="Quality settings created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "quality_id": str(quality_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Create",
                resource="Quality",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while creating quality settings")


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return decrypted_raw


def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return json.loads(decrypted_raw)


@router.get("/get/quality/{facility_id}/")
async def get_quality_settings(
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

    ce = getattr(request.app, "client_encryption", None)

    by_link = await QualityDoc.find(QualityDoc.facility_id.id == facility_obj.id).to_list()
    by_str = await QualityDoc.find(QualityDoc.facility_id == str(facility_obj.id)).to_list()

    seen = set()
    docs = []
    for d in by_link + by_str:
        if str(d.id) in seen:
            continue
        seen.add(str(d.id))
        docs.append(d)

    result = [
        {
            "id": str(q.id),
            "enable_mds_reporting": _decrypt_value(ce, q.enable_mds_reporting),
            "enable_quality_measure": _decrypt_value(ce, q.enable_quality_measure),
            "enable_infection_control_tracking": _decrypt_value(ce, q.enable_infection_control_tracking),
            "fall_risk_program": _decrypt_value(ce, q.fall_risk_program),
            "quality_reporting": _decrypt_json_field(ce, q.quality_reporting),
            "created_at": q.created_at,
            "updated_at": q.updated_at,
        } for q in docs
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Quality",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Quality settings fetched successfully",
        )
    except Exception:
        pass

    return result
