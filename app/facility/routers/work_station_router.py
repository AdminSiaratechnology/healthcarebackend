from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.ITWorkstations import WorkStationSchema
from beanie import PydanticObjectId

import json
import os
from app.facility.models.workstations import WorkStation

router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/workstation/{facility_id}/")
async def create_workstation(
    facility_id: str,
    workstation: WorkStationSchema,
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

        ws_doc = WorkStation(
            facility_id=facility,
            workstation_code=enc_or_none(workstation.work_station_code),
            location=enc_or_none(workstation.location),
            operating_system=enc_or_none(workstation.os_type),
            peripherals=enc_json_or_none(workstation.peripherals),
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await ws_doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Workstation",
                resource_id=str(ws_doc.id),
                status="success",
                notes="Workstation created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "workstation_id": str(ws_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Create",
                resource="Workstation",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while creating workstation")


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


@router.get("/get/workstation/{facility_id}/")
async def get_workstations(
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

    # ---------------- Work Stations  ----------------
    work_stations = await WorkStation.find(
        WorkStation.facility_id.id == facility_obj.id,
        WorkStation.created_by.id == user.id
    ).sort("-created_at").to_list()
   
    

    # response 

    result = [
        {
            "id": str(ws.id),
            "workstation_code": _decrypt_value(ce, ws.workstation_code),
            "location": _decrypt_value(ce, ws.location),
            "operating_system": _decrypt_value(ce, ws.operating_system),
            "peripherals": _decrypt_json_field(ce, ws.peripherals),
            "created_at": ws.created_at,
            "updated_at": ws.updated_at,
        } for ws in work_stations
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Workstation",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Workstations fetched successfully",
        )
    except Exception:
        pass

    return result



@router.put("/update/workstation/{workstation_id}/")
async def update_workstation(
    workstation_id: str,
    payload: WorkStationSchema,
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

        def enc_json_or_none(obj):
            return (
                encrypt_value(client_encryption, dek_id, json.dumps(obj.model_dump()))
                if obj is not None else None
            )

        ws_doc = await WorkStation.get(workstation_id)
        if not ws_doc:
            raise HTTPException(status_code=404, detail="Workstation not found")

        ws_doc.workstation_code = enc_or_none(payload.work_station_code)
        ws_doc.location = enc_or_none(payload.location)
        ws_doc.operating_system = enc_or_none(payload.os_type)
        ws_doc.peripherals = enc_json_or_none(payload.peripherals)
        ws_doc.updated_at = datetime.now(timezone.utc)

        await ws_doc.save()

        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Update",
                resource="Workstation",
                resource_id=str(ws_doc.id),
                status="success",
                notes="Workstation updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "workstation_id": str(ws_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Update",
                resource="Workstation",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while updating workstation")