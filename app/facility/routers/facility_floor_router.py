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
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key, encrypt_value_deterministic
import json
import os

router = APIRouter(prefix="/facility", tags=["Facility"])


def _dec_str(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode() if isinstance(raw, (bytes, bytearray)) else raw




@router.post("/create/floor/{facility_id}/")
async def create_facility_floor(
    facility_id: str,
    floor: FloorSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        # client_encryption = request.app.client_encryption
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
        dek_id = getattr(request.app, "dek_id", None)
        # ✅ Encrypt Body
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
       

        # ✅ ✅ FIXED FACILITY ID
        try:
            facility_obj_id = PydanticObjectId(facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")

        facilityid = await Facility.get(facility_obj_id)
        if not facilityid:
            raise HTTPException(status_code=404, detail="Facility not found")

        # ✅ Check User
        enc_floor_label_det = encrypt_value_deterministic(ce, dek_id, floor.floor_label)
        enc_floor_dispaly_det = encrypt_value_deterministic(ce, dek_id, floor.display)

        # ✅ Create Floor
        facility_floor_doc = FacilityFloor(
            floor_label=enc_floor_label_det,
            display=enc_floor_dispaly_det,
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
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce
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
    
    floor = await FacilityFloor.find({"facility_id.$id": facility_obj.id}).to_list()

    
    items = []
    for f in floor:
        items.append({
            "id": str(f.id),
            "floor_label":_dec_str(ce, f.floor_label),
            "display":_dec_str(ce, f.display),
        })
        

    

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

    return items


@router.put("/update/floor/{floor_id}/")
async def update_floor(
    floor_id: str,
    floor: FloorSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    # Encryption setup
    client_encryption = getattr(request.app, "client_encryption", None)
    if client_encryption is None:
        client_encryption = init_encryption()
        request.app.client_encryption = client_encryption

    dek_id = getattr(request.app, "dek_id", None)
    if dek_id is None:
        dek_id = ensure_data_key()
        request.app.dek_id = dek_id

    # Get user
    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate floor ID
    try:
        floor_obj_id = PydanticObjectId(floor_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Floor ID format")

    # Fetch floor
    fl = await FacilityFloor.get(floor_obj_id)
    if not fl:
        raise HTTPException(status_code=404, detail="Floor Label not found")

    try:
        # Encrypt and update
        enc_floor_label = encrypt_value_deterministic(
            client_encryption, dek_id, floor.floor_label
        )
        enc_floor_display= encrypt_value_deterministic(
            client_encryption, dek_id, floor.display
        )

        fl.floor_label = enc_floor_label
        fl.display = enc_floor_display
        fl.updated_at = datetime.now(timezone.utc)
        await fl.save()

        # Audit log
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Facility Floor",
                resource_id=str(fl.id),
                status="success",
                notes="Floor updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "id": str(fl.id),
            "floor_label": floor.floor_label,
            "display": floor.display,
            "updated_at": fl.updated_at,
        }

    except HTTPException:
        raise

    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Update",
                resource="Facility Floor",
                resource_id=str(floor_id),
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass

        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating floor",
        )
