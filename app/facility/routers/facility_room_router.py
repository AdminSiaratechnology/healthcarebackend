from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value,init_encryption,ensure_data_key,encrypt_value_deterministic
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


@router.get("/get/room/{facility_id}/")
async def get_facility_rooms(
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

    by_link = await FacilityRooms.find(FacilityRooms.facility_id.id == facility_obj.id).to_list()
    by_str = await FacilityRooms.find(FacilityRooms.facility_id == str(facility_obj.id)).to_list()

    seen = set()
    docs = []
    for d in by_link + by_str:
        if str(d.id) in seen:
            continue
        seen.add(str(d.id))
        docs.append(d)

    result = [
        {
            "id": str(r.id),
            "room_id": _decrypt_value(ce, r.room_id),
            "room_type": _decrypt_value(ce, r.room_type),
            "wing": _decrypt_value(ce, r.wing),
            "room_features": _decrypt_json_field(ce, r.room_features),
            "isolation_room": _decrypt_value(ce, r.isolation_room),
            "notes": _decrypt_value(ce, r.notes),
            "floor_id": str(r.floor.id) if r.floor else None,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        } for r in docs
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Facility Room",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Facility rooms fetched successfully",
        )
    except Exception:
        pass

    return result





@router.put("/update/room/{room_id}/")
async def update_facility_room(
    room_id: str,
    room: FacilityRoom,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce
    dek_id = getattr(request.app, "dek_id", None)
    if dek_id is None:
        dek_id = ensure_data_key()
        request.app.dek_id = dek_id

    def enc_or_none(val):
        return encrypt_value(ce, dek_id, val) if val is not None else None

    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        room_obj_id = PydanticObjectId(room_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Room ID format")
    room_doc = await FacilityRooms.get(room_obj_id)
    if not room_doc:
        raise HTTPException(status_code=404, detail="Room not found")

    update_data = room.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    current_room_id = _decrypt_value(ce, room_doc.room_id)
    current_type = _decrypt_value(ce, room_doc.room_type)
    current_wing = _decrypt_value(ce, room_doc.wing)
    current_features = _decrypt_json_field(ce, room_doc.room_features)
    current_isolation = _decrypt_value(ce, room_doc.isolation_room)
    current_notes = _decrypt_value(ce, room_doc.notes)

    new_room_id = room.room_id if "room_id" in update_data else current_room_id
    new_room_type = (room.room_type.value if room.room_type else None) if "room_type" in update_data else current_type
    new_wing = room.wing if "wing" in update_data else current_wing

    if "features" in update_data:
        new_features_obj = room.features
    else:
        new_features_obj = current_features

    new_isolation = room.isolation_room if "isolation_room" in update_data else current_isolation
    new_notes = room.notes if "notes" in update_data else current_notes

    room_doc.room_id = enc_or_none(new_room_id)
    room_doc.room_type = enc_or_none(new_room_type)
    room_doc.wing = enc_or_none(new_wing)
    room_doc.room_features = enc_or_none(json.dumps(new_features_obj.model_dump()) if new_features_obj is not None else None)
    room_doc.isolation_room = enc_or_none(new_isolation)
    room_doc.notes = enc_or_none(new_notes)
    room_doc.updated_at = datetime.now(timezone.utc)
    await room_doc.save()

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Update",
            resource="Facility Room",
            resource_id=str(room_doc.id),
            status="success",
            notes="Facility room updated successfully",
        )
    except Exception:
        pass

    return {
        "success": True,
        "id": str(room_doc.id),
        "room_id": new_room_id,
        "room_type": new_room_type,
        "wing": new_wing,
        "room_features": new_features_obj.model_dump() if new_features_obj is not None else None,
        "isolation_room": new_isolation,
        "notes": new_notes,
        "floor_id": str(room_doc.floor.id) if room_doc.floor else None,
        "created_at": room_doc.created_at,
        "updated_at": room_doc.updated_at,
    }
