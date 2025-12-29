from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.Imaging_center import ImagingCenterSchema   
from beanie import PydanticObjectId

import json
import os
from app.facility.models.imaging_center import ImagingCenter


router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/imaging-center/{facility_id}/")
async def create_imaging_center(
    facility_id: str,
    center: ImagingCenterSchema,
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

        center_doc = ImagingCenter(
            facility_id=facility,
            center_name=enc_or_none(center.center_name),
            phone=enc_or_none(center.phone),
            fax=enc_or_none(center.fax),
            turnaround_time=enc_or_none(center.turnaround_time),
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await center_doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Imaging Center",
                resource_id=str(center_doc.id),
                status="success",
                notes="Imaging center created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "imaging_center_id": str(center_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Create",
                resource="Imaging Center",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while creating imaging center")


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return decrypted_raw


@router.get("/get/imaging-center/{facility_id}/")
async def get_imaging_centers(
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
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    # ---------------- Imaging Center  ----------------
    imaging_center = await ImagingCenter.find(
        ImagingCenter.facility_id.id == facility_obj.id,
        ImagingCenter.created_by.id == user.id
    ).sort("-created_at").to_list()
   
   


   

    result = [
        {
            "id": str(ic.id),
            "center_name": _decrypt_value(ce, ic.center_name),
            "phone": _decrypt_value(ce, ic.phone),
            "fax": _decrypt_value(ce, ic.fax),
            "turnaround_time": _decrypt_value(ce, ic.turnaround_time),
            "transport_notes": _decrypt_value(ce, ic.transport_notes),
            "created_at": ic.created_at,
            "updated_at": ic.updated_at,
        } for ic in imaging_center
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Imaging Center",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Imaging centers fetched successfully",
        )
    except Exception:
        pass

    return result
