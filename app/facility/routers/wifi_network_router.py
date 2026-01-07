from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.ITWorkstations import WifiNetworkSchema
from beanie import PydanticObjectId

import json
import os
from app.facility.models.wifi_network import WifiNetwork

router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/wifi-network/{facility_id}/")
async def create_wifi_network(
    facility_id: str,
    wifi: WifiNetworkSchema,
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

        wifi_doc = WifiNetwork(
            facility_id=facility,
            ssid=enc_or_none(wifi.ssid),
            password=enc_or_none(wifi.password),
            guest_network=enc_or_none(wifi.guest_network),
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await wifi_doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Wifi Network",
                resource_id=str(wifi_doc.id),
                status="success",
                notes="Wifi network created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "wifi_network_id": str(wifi_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Create",
                resource="Wifi Network",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while creating wifi network")


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return decrypted_raw


@router.get("/get/wifi-network/{facility_id}/")
async def get_wifi_networks(
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

        # ---------------- Wifi Network  ----------------
    wifi_network = await WifiNetwork.find(
        WifiNetwork.facility_id.id == facility_obj.id,
        WifiNetwork.created_by.id == user.id
    ).sort("-created_at").to_list()
   

   

    # Response 


    result = [
        {
            "id": str(wf.id),
            "ssid": _decrypt_value(ce, wf.ssid),
            "password": _decrypt_value(ce, wf.password),
            "guest_network": _decrypt_value(ce, wf.guest_network),
            "created_at": wf.created_at,
            "updated_at": wf.updated_at,
        } for wf in wifi_network
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Wifi Network",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Wifi networks fetched successfully",
        )
    except Exception:
        pass

    return result



@router.put("/update/wifi-network/{network_id}/")
async def update_wifi_network(
    network_id: str,
    payload: WifiNetworkSchema,
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

        wifi_doc = await WifiNetwork.get(PydanticObjectId(network_id))
        if not wifi_doc:
            raise HTTPException(status_code=404, detail="Wifi Network not found")

        wifi_doc.ssid = enc_or_none(payload.ssid)
        wifi_doc.password = enc_or_none(payload.password)
        wifi_doc.guest_network = enc_or_none(payload.guest_network)
        wifi_doc.updated_at = datetime.now(timezone.utc)

        await wifi_doc.save()

        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Update",
                resource="Wifi Network",
                resource_id=str(wifi_doc.id),
                status="success",
                notes="Wifi network updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "wifi_network_id": str(wifi_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Update",
                resource="Wifi Network",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while updating wifi network")