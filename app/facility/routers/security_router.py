from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.security import SecuritySchema
from beanie import PydanticObjectId
import json
import os
from app.facility.models.security import SecurityDoc

router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/security/{facility_id}/")
async def create_security(
    facility_id: str,
    sec: SecuritySchema,
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

        doc = SecurityDoc(
            facility_id=facility,
            user_roles_access=enc_json_or_none(sec.user_roles_access),
            authentication_sessions=enc_json_or_none(sec.authentication_sessions),
            phi_export_controls=enc_json_or_none(sec.phi_export_settings),
            breakglass_procedures=enc_json_or_none(sec.break_glass_audit),
            privacy_policies=enc_json_or_none(sec.privacy_officer_info),
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
                resource="Security",
                resource_id=str(doc.id),
                status="success",
                notes="Facility security settings created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "security_id": str(doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Create",
                resource="Security",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while creating security settings")


def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return json.loads(decrypted_raw)


@router.get("/get/security/{facility_id}/")
async def get_security_settings(
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

    by_link = await SecurityDoc.find(SecurityDoc.facility_id.id == facility_obj.id).to_list()
    by_str = await SecurityDoc.find(SecurityDoc.facility_id == str(facility_obj.id)).to_list()

    seen = set()
    docs = []
    for d in by_link + by_str:
        if str(d.id) in seen:
            continue
        seen.add(str(d.id))
        docs.append(d)

    result = [
        {
            "id": str(sc.id),
            "user_roles_access": _decrypt_json_field(ce, sc.user_roles_access),
            "authentication_sessions": _decrypt_json_field(ce, sc.authentication_sessions),
            "phi_export_controls": _decrypt_json_field(ce, sc.phi_export_controls),
            "breakglass_procedures": _decrypt_json_field(ce, sc.breakglass_procedures),
            "privacy_policies": _decrypt_json_field(ce, sc.privacy_policies),
            "created_at": sc.created_at,
            "updated_at": sc.updated_at,
        } for sc in docs
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Security",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Security settings fetched successfully",
        )
    except Exception:
        pass

    return result
