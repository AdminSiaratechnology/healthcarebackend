from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
# from app.schemas.facility import FacilityPayload

from app.facility.models.facility import Facility
from app.facility.models.facility_floor import FacilityFloor

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value
from app.utils.audit import log_audit
from app.schemas.facilities.floor import FloorSchema
from beanie import PydanticObjectId

import json
import os

router = APIRouter(prefix="/facility", tags=["Facility"])


def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return json.loads(decrypted_raw)

from beanie import PydanticObjectId

@router.post("/create/floor/{facility_id}/")
async def create_facility_floor(
    facility_id: str,
    floor: FloorSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        client_encryption = request.app.client_encryption
        dek_id = request.app.dek_id

        # ✅ Encrypt Body
        try:
            body = json.dumps(floor.model_dump())
            enc_struct = encrypt_value(client_encryption, dek_id, body)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Encryption failed: {str(e)}")

        # ✅ ✅ FIXED FACILITY ID
        try:
            facility_obj_id = PydanticObjectId(facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")

        facilityid = await Facility.get(facility_obj_id)
        if not facilityid:
            raise HTTPException(status_code=404, detail="Facility not found")

        # ✅ Check User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # ✅ Create Floor
        facility_floor_doc = FacilityFloor(
            floor_label=enc_struct,
            display=enc_struct,
            facility_id=str(facilityid.id),
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await facility_floor_doc.insert()

        # ✅ Audit Log
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Facility Floor",
                resource_id=str(facility_floor_doc.id),
                status="success",
                notes="Facility floor created successfully",
            )
        except Exception as audit_error:
            print("⚠️ Audit Log Failed:", audit_error)

        return {
            "success": True,
            "facility_id_received": str(facilityid.id),
            "facility_floor_id": str(facility_floor_doc.id),
        }

    except HTTPException:
        raise

    except Exception as e:
        print("❌ Facility Floor Create Crash:", repr(e))
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility floor"
        )


@router.get("/get/floor/{facility_id}/")
async def get_facility_floors(
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

    ce = request.app.client_encryption

    by_link = await FacilityFloor.find(FacilityFloor.facility_id.id == facility_obj.id).to_list()
    by_str = await FacilityFloor.find(FacilityFloor.facility_id == str(facility_obj.id)).to_list()

    seen = set()
    docs = []
    for d in by_link + by_str:
        if str(d.id) in seen:
            continue
        seen.add(str(d.id))
        docs.append(d)

    result = [
        {
            "id": str(f.id),
            "floor_label": _decrypt_json_field(ce, f.floor_label),
            "display": _decrypt_json_field(ce, f.display),
            "created_at": f.created_at,
            "updated_at": f.updated_at,
        } for f in docs
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Facility Floor",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Facility floors fetched successfully",
        )
    except Exception:
        pass

    return result
