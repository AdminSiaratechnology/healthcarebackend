from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.ITWorkstations import DeviceInventorySchema
from beanie import PydanticObjectId

import json
import os
from app.facility.models.DeviceInventory import DeviceInventory

router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/device-inventory/{facility_id}/")
async def create_device_inventory(
    facility_id: str,
    device: DeviceInventorySchema,
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
            if val is None:
                return None
            if hasattr(val, "value"):
                val = val.value
            return encrypt_value(client_encryption, dek_id, val)

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

        di_doc = DeviceInventory(
            facility_id=facility,
            device_type=enc_or_none(device.device_type),
            counts=enc_or_none(device.count),
            operating_system=enc_or_none(device.operating_system),
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await di_doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Device Inventory",
                resource_id=str(di_doc.id),
                status="success",
                notes="Device inventory created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "device_inventory_id": str(di_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Create",
                resource="Device Inventory",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while creating device inventory")


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return decrypted_raw


@router.get("/get/device-inventory/{facility_id}/")
async def get_device_inventories(
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

     # encrypt 
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    # ---------------- Device Inventory  ----------------
    device_inventory = await DeviceInventory.find(
        DeviceInventory.facility_id.id == facility_obj.id,
        DeviceInventory.created_by.id == user.id
    ).sort("-created_at").to_list()
   


    # response 
    result = [
        {
            "id": str(di.id),
            "device_type": _decrypt_value(ce, di.device_type),
            "count": _decrypt_value(ce, di.counts),
            "operating_system": _decrypt_value(ce, di.operating_system),
            "created_at": di.created_at,
            "updated_at": di.updated_at,
        } for di in device_inventory
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Device Inventory",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Device inventories fetched successfully",
        )
    except Exception:
        pass

    return result
