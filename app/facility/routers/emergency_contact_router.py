from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.emergency_contact import emergency_contact_Schema
from beanie import PydanticObjectId

import json
import os
from app.facility.models.emergency_contact import EmergencyContactDocs
from fastapi import APIRouter

router = APIRouter(prefix="/facility", tags=["Facility"])


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw


@router.post("/emergency-contact/create/{facility_id}/")
async def create_emergency_contact(
    facility_id: str,
    payload: emergency_contact_Schema,
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

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        enc_role = encrypt_value(ce, dek_id, payload.role) if payload.role is not None else None
        enc_phone = encrypt_value(ce, dek_id, payload.phone) if payload.phone is not None else None
        enc_after_hour = encrypt_value(ce, dek_id, payload.after_hour) if payload.after_hour is not None else None

        doc = EmergencyContactDocs(
            facility_id=facility_obj,
            role=enc_role,
            phone=enc_phone,
            after_hour=enc_after_hour,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await doc.insert()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Create",
            resource="Emergency Contact",
            resource_id=str(doc.id),
            status="success",
            notes="Emergency contact created",
        )

        return {"status": "success","id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Create",
                resource="Emergency Contact",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/emergency-contact/get/{facility_id}/")
async def get_emergency_contacts(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    # ---------------- USER ----------------
    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ---------------- FACILITY ----------------
    try:
        facility = await Facility.get(PydanticObjectId(facility_id))
    except Exception:
        facility = await Facility.get(facility_id)

    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")

    # ---------------- ENCRYPTION ----------------
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    # ---------------- EMERGENCY CONTACTS ----------------
    contacts = await EmergencyContactDocs.find(
        EmergencyContactDocs.facility_id.id == facility.id,
        EmergencyContactDocs.created_by.id == user.id
    ).sort("-created_at").to_list()

    # ---------------- RESPONSE ----------------
    result = [
        {
            "id": str(ec.id),
            "role": _decrypt_value(ce, ec.role),
            "phone": _decrypt_value(ce, ec.phone),
            "after_hour": _decrypt_value(ce, ec.after_hour),
            "created_at": ec.created_at,
            "updated_at": ec.updated_at,
        } for ec in contacts
    ]

    # ---------------- AUDIT ----------------
    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Emergency Contact",
            resource_id=str(facility.id),
            status="success",
            notes="Emergency contacts fetched successfully",
        )
    except Exception:
        pass

    return result



@router.put("/emergency-contact/update/{contact_id}/")
async def update_emergency_contact(
    contact_id: str,
    payload: emergency_contact_Schema,
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

        contact_obj = None
        try:
            contact_obj_id = PydanticObjectId(contact_id)
            contact_obj = await EmergencyContactDocs.get(contact_obj_id)
        except Exception:
            pass
        if contact_obj is None:
            contact_obj = await EmergencyContactDocs.get(contact_id)
        if not contact_obj:
            raise HTTPException(status_code=404, detail="Emergency Contact not found")

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if payload.role is not None:
            contact_obj.role = encrypt_value(ce, dek_id, payload.role)
        if payload.phone is not None:
            contact_obj.phone = encrypt_value(ce, dek_id, payload.phone)
        if payload.after_hour is not None:
            contact_obj.after_hour = encrypt_value(ce, dek_id, payload.after_hour)

        contact_obj.updated_at = datetime.now(timezone.utc)
        await contact_obj.save()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Update",
            resource="Emergency Contact",
            resource_id=str(contact_obj.id),
            status="success",
            notes="Emergency contact updated",
        )

        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Update",
                resource="Emergency Contact",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
