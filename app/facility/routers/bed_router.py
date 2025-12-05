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
