from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value,init_encryption,ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.bed import Bed
from beanie import PydanticObjectId

import json
import os
from app.facility.models.beds import Beds
from beanie.operators import In


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
             facility_id=facility_obj_id,
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


# @router.get("/get/bed/{facility_id}/")
# async def get_beds(
#     facility_id: str,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id)
# ):
#     user = await UserDoc.get(current_user_id)
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     facility_obj = None
#     try:
#         facility_obj_id = PydanticObjectId(facility_id)
#         facility_obj = await Facility.get(facility_obj_id)
#     except Exception:
#         pass

#     if facility_obj is None:
#         facility_obj = await Facility.get(facility_id)
#     if not facility_obj:
#         raise HTTPException(status_code=404, detail="Facility not found")

#     ce = request.app.client_encryption

#     rooms_by_link = await FacilityRooms.find(FacilityRooms.facility_id.id == facility_obj.id).to_list()
#     rooms_by_str = await FacilityRooms.find(FacilityRooms.facility_id == str(facility_obj.id)).to_list()

#     seen_r = set()
#     rooms = []
#     for r in rooms_by_link + rooms_by_str:
#         if str(r.id) in seen_r:
#             continue
#         seen_r.add(str(r.id))
#         rooms.append(r)

#     beds_for_facility = []
#     seen_b = set()
#     for r in rooms:
#         rr_beds = await Beds.find(Beds.room_id.id == r.id).to_list()
#         for b in rr_beds:
#             if str(b.id) in seen_b:
#                 continue
#             seen_b.add(str(b.id))
#             beds_for_facility.append(b)

#     result = [
#         {
#             "id": str(b.id),
#             "bed_id": _decrypt_value(ce, b.bed_id),
#             "designation": _decrypt_value(ce, b.designation),
#             "status": _decrypt_value(ce, b.status),
#             "bariatric": _decrypt_value(ce, b.bariatric),
#             "room_id": (str((await b.room_id.fetch()).id) if b.room_id else None),
#             "last_sanitized": b.last_sanitized,
#             "bed_policy": _decrypt_value(ce, b.bed_policy),
#             "created_at": b.created_at,
#             "updated_at": b.updated_at,
#         } for b in beds_for_facility
#     ]

#     try:
#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Read",
#             resource="Bed",
#             resource_id=str(facility_obj.id),
#             status="success",
#             notes="Beds fetched successfully",
#         )
#     except Exception:
#         pass

#     return result


@router.get("/get/bed/{facility_id}/")
async def get_beds(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    # ---------------- USER ----------------
    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ---------------- FACILITY ----------------
    facility = None
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

    # ---------------- ROOMS (facility + created_by) ----------------
    rooms = await FacilityRooms.find(
        FacilityRooms.facility_id.id == facility.id,
        FacilityRooms.created_by.id == user.id
    ).to_list()

    if not rooms:
        return []

    room_ids = [r.id for r in rooms]

    # ---------------- BEDS (room + created_by) ----------------
    beds = await Beds.find(
        In(Beds.room_id.id, room_ids),
        Beds.created_by.id == user.id
    ).sort("-created_at").to_list()

    # ---------------- RESPONSE ----------------
    result = []
    for bed in beds:
        room_id = None
        if bed.room_id:
            try:
                room = await bed.room_id.fetch()
                room_id = str(room.id)
            except Exception:
                pass

        result.append({
            "id": str(bed.id),
            "bed_id": _decrypt_value(ce, bed.bed_id),
            "designation": _decrypt_value(ce, bed.designation),
            "status": _decrypt_value(ce, bed.status),
            "bariatric": _decrypt_value(ce, bed.bariatric),
            "room_id": room_id,
            "last_sanitized": bed.last_sanitized,
            "bed_policy": _decrypt_value(ce, bed.bed_policy),
            "created_at": bed.created_at,
            "updated_at": bed.updated_at,
        })

    # ---------------- AUDIT ----------------
    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Bed",
            resource_id=str(facility.id),
            status="success",
            notes="Beds fetched successfully",
        )
    except Exception:
        pass

    return result



@router.get("/get/bed/by-room/{room_id}/")
async def get_beds_by_room(
    room_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    room_obj = None
    try:
        room_obj_id = PydanticObjectId(room_id)
        room_obj = await FacilityRooms.get(room_obj_id)
    except Exception:
        pass

    if room_obj is None:
        room_obj = await FacilityRooms.get(room_id)
    if not room_obj:
        raise HTTPException(status_code=404, detail="Room not found")

    ce = request.app.client_encryption

    beds_by_link = await Beds.find(Beds.room_id.id == room_obj.id).to_list()
    beds_by_str = await Beds.find(Beds.room_id == str(room_obj.id)).to_list()

    seen = set()
    beds = []
    for b in beds_by_link + beds_by_str:
        if str(b.id) in seen:
            continue
        seen.add(str(b.id))
        beds.append(b)

    async def _safe_room_id(bed_doc):
        if not bed_doc.room_id:
            return None
        if hasattr(bed_doc.room_id, "fetch"):
            try:
                return str((await bed_doc.room_id.fetch()).id)
            except Exception:
                pass
        return str(getattr(bed_doc.room_id, "id", bed_doc.room_id))

    result = [
        {
            "id": str(b.id),
            "bed_id": _decrypt_value(ce, b.bed_id),
            "designation": _decrypt_value(ce, b.designation),
            "status": _decrypt_value(ce, b.status),
            "bariatric": _decrypt_value(ce, b.bariatric),
            "room_id": await _safe_room_id(b),
            "last_sanitized": b.last_sanitized,
            "bed_policy": _decrypt_value(ce, b.bed_policy),
            "created_at": b.created_at,
            "updated_at": b.updated_at,
        } for b in beds
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Bed",
            resource_id=str(room_obj.id),
            status="success",
            notes="Beds fetched successfully by room",
        )
    except Exception:
        pass

    return result



@router.put("/update/bed/{bed_id}/")
async def update_bed(
    bed_id: str,
    bed: Bed,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    print("heloooooooooooo")
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
        bed_obj_id = PydanticObjectId(bed_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Bed ID format")
    bed_doc = await Beds.get(bed_obj_id)
    if not bed_doc:
        raise HTTPException(status_code=404, detail="Bed not found")
    update_data = bed.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided for update")
    
    current_bed_id = _decrypt_value(ce, bed_doc.bed_id)
    current_designation = _decrypt_value(ce, bed_doc.designation)
    current_status = _decrypt_value(ce, bed_doc.status)
    current_bariatric = _decrypt_value(ce, bed_doc.bariatric)
    current_last_sanitized = _decrypt_value(ce, bed_doc.last_sanitized)
    current_bed_policy = _decrypt_value(ce, bed_doc.bed_policy)
    room_id = bed.room_id

    new_bed_id = bed.bed_id if "bed_id" in update_data else current_bed_id
    new_designation = bed.designation if "designation" in update_data else current_designation
    new_status = bed.status if "status" in update_data else current_status
    new_bariatric = bed.bariatric if "status" in update_data else current_bariatric
    new_bed_policy = bed.move_policy if "status" in update_data else current_bed_policy

    print("status",new_status)

    bed_doc.bed_id = enc_or_none(new_bed_id)
    
    bed_doc.designation = enc_or_none(new_designation)
    bed_doc.status = enc_or_none(new_status)
    bed_doc.bariatric = enc_or_none(new_bariatric)
    bed_doc.bed_policy = enc_or_none(new_bed_policy)
    bed_doc.updated_at = datetime.now(timezone.utc)

    room = await FacilityRooms.get(PydanticObjectId(room_id))
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    bed_doc.room_id = room
    await bed_doc.save()
    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Update",
            resource="Facility Bed",
            resource_id=str(bed_doc.id),
            status="success",
            notes="Facility Bed updated successfully",
        )
    except Exception:
        pass

    return {
        "success": True,
        "id": str(bed_doc.id),
        "bed_id": new_bed_id,
        "designation": new_designation,
        "status": new_status,
        "bariatric": new_bariatric,
        "policy": new_bed_policy,
        "created_at": bed_doc.created_at,
        "updated_at": bed_doc.updated_at,
    }

   

   
    

   

   