from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError


from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.device.device import DeviceCreateSchema,BlockAllDevicesSchema,LogoutAllDevicesSchema
from beanie import PydanticObjectId

import json
import os
from app.device.models.device import DeviceDoc


router = APIRouter(prefix="/device", tags=["Devices"])


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw


@router.post("/create/")
async def create_device(
    payload: DeviceCreateSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce
        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        enc_device_name = encrypt_value(ce, dek_id, payload.device_name) if payload.device_name else None
        enc_device_type = encrypt_value(ce, dek_id, payload.device_type) if payload.device_type else None
        enc_platform = encrypt_value(ce, dek_id, payload.platform) if payload.platform else None
        enc_os_version = encrypt_value(ce, dek_id, payload.os_version) if payload.os_version else None
        enc_app_version = encrypt_value(ce, dek_id, payload.app_version) if payload.app_version else None
        enc_battery = encrypt_value(ce, dek_id, payload.battery_percentage) if payload.battery_percentage is not None else None
        enc_location = encrypt_value(ce, dek_id, payload.location) if payload.location else None
        enc_is_current = encrypt_value(ce, dek_id, payload.is_current_device) if payload.is_current_device is not None else None
        enc_status = encrypt_value(ce, dek_id, "Active")

        doc = DeviceDoc(
            created_by=user,
            device_name=enc_device_name,
            device_type=enc_device_type,
            platform=enc_platform,
            os_version=enc_os_version,
            app_version=enc_app_version,
            battery_percentage=enc_battery,
            location=enc_location,
            is_current_device=enc_is_current,
            status=enc_status,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Device",
                resource_id=str(doc.id),
                status="success",
                notes="Device registered",
            )
        except Exception:
            pass

        return {"id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Create",
                resource="Device",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get/")
async def get_my_devices(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        by_link = await DeviceDoc.find(DeviceDoc.created_by.id == user.id).to_list()
        by_str = await DeviceDoc.find(DeviceDoc.created_by == str(user.id)).to_list()

        seen = set()
        docs = []
        for d in by_link + by_str:
            if str(d.id) in seen:
                continue
            seen.add(str(d.id))
            docs.append(d)

        result = []
        for dev in docs:
            result.append({
                "id": str(dev.id),
                "device_name": _decrypt_value(ce, dev.device_name),
                "device_type": _decrypt_value(ce, dev.device_type),
                "platform": _decrypt_value(ce, dev.platform),
                "os_version": _decrypt_value(ce, dev.os_version),
                "app_version": _decrypt_value(ce, dev.app_version),
                "battery_percentage": _decrypt_value(ce, dev.battery_percentage),
                "location": _decrypt_value(ce, dev.location),
                "is_current_device": _decrypt_value(ce, dev.is_current_device),
                "status": _decrypt_value(ce, dev.status),
                "last_active_at": dev.last_active_at,
                "created_at": dev.created_at,
                "updated_at": dev.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Device",
                resource_id=str(user.id),
                status="success",
                notes="Devices fetched",
            )
        except Exception:
            pass

        return result
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Read",
                resource="Device",
                resource_id="self",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get/{device_id}/")
async def get_device_by_id(
    device_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        dev = None
        try:
            d_oid = PydanticObjectId(device_id)
            dev = await DeviceDoc.get(d_oid)
        except Exception:
            dev = await DeviceDoc.get(device_id)

        if not dev:
            raise HTTPException(status_code=404, detail="Device not found")

        result = {
            "id": str(dev.id),
            "device_name": _decrypt_value(ce, dev.device_name),
            "device_type": _decrypt_value(ce, dev.device_type),
            "platform": _decrypt_value(ce, dev.platform),
            "os_version": _decrypt_value(ce, dev.os_version),
            "app_version": _decrypt_value(ce, dev.app_version),
            "battery_percentage": _decrypt_value(ce, dev.battery_percentage),
            "location": _decrypt_value(ce, dev.location),
            "is_current_device": _decrypt_value(ce, dev.is_current_device),
            "status": _decrypt_value(ce, dev.status),
            "last_active_at": dev.last_active_at,
            "created_at": dev.created_at,
            "updated_at": dev.updated_at,
        }

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Device",
                resource_id=str(dev.id),
                status="success",
                notes="Device fetched",
            )
        except Exception:
            pass

        return result
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Read",
                resource="Device",
                resource_id=device_id,
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/block-all/")
async def block_all_devices(
    payload: BlockAllDevicesSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce
        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        by_link = await DeviceDoc.find(DeviceDoc.created_by.id == user.id).to_list()
        by_str = await DeviceDoc.find(DeviceDoc.created_by == str(user.id)).to_list()

        seen = set()
        devices = []
        for d in by_link + by_str:
            if str(d.id) in seen:
                continue
            seen.add(str(d.id))
            devices.append(d)

        updated_ids = []
        for dev in devices:
            is_current = _decrypt_value(ce, dev.is_current_device)
            if not payload.block_current_device and bool(is_current):
                continue
            dev.status = encrypt_value(ce, dek_id, "Block")
            dev.updated_at = datetime.now(timezone.utc)
            await dev.save()
            updated_ids.append(str(dev.id))

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Device",
                resource_id=str(user.id),
                status="success",
                notes=f"Blocked devices: {len(updated_ids)}",
            )
        except Exception:
            pass

        return {"blocked_device_ids": updated_ids}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Update",
                resource="Device",
                resource_id="self",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logout-all/")
async def logout_all_devices(
    payload: LogoutAllDevicesSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce
        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        by_link = await DeviceDoc.find(DeviceDoc.created_by.id == user.id).to_list()
        by_str = await DeviceDoc.find(DeviceDoc.created_by == str(user.id)).to_list()

        seen = set()
        devices = []
        for d in by_link + by_str:
            if str(d.id) in seen:
                continue
            seen.add(str(d.id))
            devices.append(d)

        updated_ids = []
        for dev in devices:
            is_current = _decrypt_value(ce, dev.is_current_device)
            if not payload.logout_current_device and bool(is_current):
                continue
            dev.is_current_device = encrypt_value(ce, dek_id, False)
            dev.updated_at = datetime.now(timezone.utc)
            await dev.save()
            updated_ids.append(str(dev.id))

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Device",
                resource_id=str(user.id),
                status="success",
                notes=f"Logged out devices: {len(updated_ids)}",
            )
        except Exception:
            pass

        return {"logged_out_device_ids": updated_ids}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Update",
                resource="Device",
                resource_id="self",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
