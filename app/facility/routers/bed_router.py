from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value
from app.utils.audit import log_audit
from app.schemas.facilities.bed import Bed
from beanie import PydanticObjectId

import json
import os
from app.facility.models.beds import Beds


router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/bed/{facility_id}/")
async def create_bed(
    facility_id: str,
    bed: Bed,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        client_encryption = request.app.client_encryption
        dek_id = request.app.dek_id

        def enc_or_none(val):
            return encrypt_value(client_encryption, dek_id, val) if val is not None else None

        bed_id_enc = enc_or_none(bed.bed_id)
        designation_enc = enc_or_none(bed.designation)
        status_enc = enc_or_none(bed.status.value if bed.status else None)
        bariatric_enc = enc_or_none(bed.bariatric)

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

        room_link = None
        if bed.room_id:
            try:
                room_obj_id = PydanticObjectId(bed.room_id)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid Room ID format")
            room_doc = await FacilityRooms.get(room_obj_id)
            if not room_doc:
                raise HTTPException(status_code=404, detail="Room not found")
            room_link = room_doc

        bed_doc = Beds(
            bed_id=bed_id_enc,
            created_by=user,
            room_id=room_link,
            designation=designation_enc,
            status=status_enc,
            bariatric=bariatric_enc,
        )

        await bed_doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Bed",
                resource_id=str(bed_doc.id),
                status="success",
                notes="Bed created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "bed_id": str(bed_doc.id),
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating bed"
        )


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return decrypted_raw


@router.get("/get/bed/{facility_id}/")
async def get_beds(
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

    rooms_by_link = await FacilityRooms.find(FacilityRooms.facility_id.id == facility_obj.id).to_list()
    rooms_by_str = await FacilityRooms.find(FacilityRooms.facility_id == str(facility_obj.id)).to_list()

    seen_r = set()
    rooms = []
    for r in rooms_by_link + rooms_by_str:
        if str(r.id) in seen_r:
            continue
        seen_r.add(str(r.id))
        rooms.append(r)

    beds_for_facility = []
    seen_b = set()
    for r in rooms:
        rr_beds = await Beds.find(Beds.room_id.id == r.id).to_list()
        for b in rr_beds:
            if str(b.id) in seen_b:
                continue
            seen_b.add(str(b.id))
            beds_for_facility.append(b)

    result = [
        {
            "id": str(b.id),
            "bed_id": _decrypt_value(ce, b.bed_id),
            "designation": _decrypt_value(ce, b.designation),
            "status": _decrypt_value(ce, b.status),
            "bariatric": _decrypt_value(ce, b.bariatric),
            "room_id": (str((await b.room_id.fetch()).id) if b.room_id else None),
            "last_sanitized": b.last_sanitized,
            "bed_policy": _decrypt_value(ce, b.bed_policy),
            "created_at": b.created_at,
            "updated_at": b.updated_at,
        } for b in beds_for_facility
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Bed",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Beds fetched successfully",
        )
    except Exception:
        pass

    return result
