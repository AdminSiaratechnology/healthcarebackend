from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.ITWorkstations import NetworkConfigSchema
from beanie import PydanticObjectId

import json
import os
from app.facility.models.network_config import NetworkConfig


router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/network-config/{facility_id}/")
async def create_network_config(
    facility_id: str,
    config: NetworkConfigSchema,
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

        cfg_doc = NetworkConfig(
            facility_id=facility,
            primary_isp=enc_or_none(config.primary_isp),
            secondary_isp=enc_or_none(config.secondary_isp),
            bandwidth=enc_or_none(config.bandwidth),
            vpn_required=enc_or_none(config.vpn_required),
            printer_routing_map=enc_json_or_none(config.printer_routing_map),
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await cfg_doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Network Config",
                resource_id=str(cfg_doc.id),
                status="success",
                notes="Network configuration created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "network_config_id": str(cfg_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Create",
                resource="Network Config",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while creating network config")


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


@router.get("/get/network-config/{facility_id}/")
async def get_network_configs(
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
    
    # ---------------- Network Config  ----------------
    netwrok_config = await NetworkConfig.find(
        NetworkConfig.facility_id.id == facility_obj.id,
        NetworkConfig.created_by.id == user.id
    ).sort("-created_at").to_list()
   

    # Response 
   
    result = [
        {
            "id": str(cfg.id),
            "primary_isp": _decrypt_value(ce, cfg.primary_isp),
            "secondary_isp": _decrypt_value(ce, cfg.secondary_isp),
            "bandwidth": _decrypt_value(ce, cfg.bandwidth),
            "vpn_required": _decrypt_value(ce, cfg.vpn_required),
            "printer_routing_map": _decrypt_json_field(ce, cfg.printer_routing_map),
            "created_at": cfg.created_at,
            "updated_at": cfg.updated_at,
        } for cfg in netwrok_config
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Network Config",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Network configurations fetched successfully",
        )
    except Exception:
        pass

    return result
