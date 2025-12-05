from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value
from app.utils.audit import log_audit
from app.schemas.facilities.rooms import FacilityRoom
from beanie import PydanticObjectId

import json
import os


router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/room/{facility_id}/")
async def create_facility_room(
    facility_id: str,
    room: FacilityRoom,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        client_encryption = request.app.client_encryption
        dek_id = request.app.dek_id

        def enc_or_none(val):
            return encrypt_value(client_encryption, dek_id, val) if val is not None else None

        room_id_enc = enc_or_none(room.room_id)
        room_type_enc = enc_or_none(room.room_type.value if room.room_type else None)
        wing_enc = enc_or_none(room.wing)
        features_enc = enc_or_none(json.dumps(room.features.model_dump()) if room.features else None)
        isolation_enc = enc_or_none(room.isolation_room)
        notes_enc = enc_or_none(room.notes)

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

        room_doc = FacilityRooms(
            room_id=room_id_enc,
            room_type=room_type_enc,
            wing=wing_enc,
            room_features=features_enc,
            isolation_room=isolation_enc,
            notes=notes_enc,
            facility_id=facility,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await room_doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Facility Room",
                resource_id=str(room_doc.id),
                status="success",
                notes="Facility room created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "facility_room_id": str(room_doc.id),
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility room"
        )
