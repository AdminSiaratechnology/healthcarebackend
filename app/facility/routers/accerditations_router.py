from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.accreditations import AccreditationsSchema
from beanie import PydanticObjectId
import json
import os
from app.facility.models.accreditations import AccerditationsDoc


router = APIRouter(prefix="/facility", tags=["Facility"])


def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return json.loads(decrypted_raw)


@router.post("/create/accreditations/{facility_id}/")
async def create_accreditations(
    facility_id: str,
    acc: AccreditationsSchema,
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

        def enc_json_or_none(val):
            return (
                encrypt_value(
                    client_encryption,
                    dek_id,
                    json.dumps(val)
                ) if val is not None else None
            )

        acc_body = acc.accreditations.value if acc.accreditations is not None else None
        status_val = acc.status.value if acc.status is not None else None
        expiry_val = acc.expiry_date.isoformat() if acc.expiry_date is not None else None
        cert_id = acc.certificate_file_id if acc.certificate_file_id is not None else None

        doc = AccerditationsDoc(
            facility_id=facility,
            accreditations=enc_json_or_none(acc_body),
            status=enc_json_or_none(status_val),
            expiry_date=enc_json_or_none(expiry_val),
            certificate_file_id=enc_json_or_none(cert_id),
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
                resource="Accreditations",
                resource_id=str(doc.id),
                status="success",
                notes="Accreditations created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "accreditations_id": str(doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Create",
                resource="Accreditations",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while creating accreditations")


@router.get("/get/accreditations/{facility_id}/")
async def get_accreditations(
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

    by_link = await AccerditationsDoc.find(AccerditationsDoc.facility_id.id == facility_obj.id).to_list()
    by_str = await AccerditationsDoc.find(AccerditationsDoc.facility_id == str(facility_obj.id)).to_list()

    seen = set()
    docs = []
    for d in by_link + by_str:
        if str(d.id) in seen:
            continue
        seen.add(str(d.id))
        docs.append(d)

    result = [
        {
            "id": str(acd.id),
            "accreditations": _decrypt_json_field(ce, acd.accreditations),
            "status": _decrypt_json_field(ce, acd.status),
            "expiry_date": _decrypt_json_field(ce, acd.expiry_date),
            "certificate_file_id": _decrypt_json_field(ce, acd.certificate_file_id),
            "created_at": acd.created_at,
            "updated_at": acd.updated_at,
        } for acd in docs
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Accreditations",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Accreditations fetched successfully",
        )
    except Exception:
        pass

    return result
