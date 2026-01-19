from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Request, HTTPException, Depends,Query
from pydantic import ValidationError
from beanie.operators import RegEx,And,Or
from typing import Optional

from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value,init_encryption,ensure_data_key,encrypt_value_deterministic,encrypt_dict
from app.utils.audit import log_audit
from app.schemas.facilities.rooms import FacilityRoom
from beanie import PydanticObjectId
import re

import json
import os



router = APIRouter(prefix="/rooms", tags=["Masters"])


@router.post("/create/{facility_id}/")
async def create_facility_room(
    facility_id: str,
    payload: FacilityRoom,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    
):
    try:
        # 1️⃣ User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 2️⃣ Encryption init  

        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce
       

        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

         # 3️⃣ Facility ownership check
        facility = await Facility.find_one(
            Facility.id == ObjectId(facility_id),
            Facility.created_by.id == user.id,
        )
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        # 4️⃣ Normalize name (VERY IMPORTANT)
        normalized_room_no = payload.room_id.strip().lower()
        normalized_room_type = payload.room_type.strip().lower()

        # 5️⃣Duplicate validation (ACTIVE RECORDS ONLY)

        existing = await FacilityRooms.find_one(
            FacilityRooms.facility_id.id == facility.id,
            FacilityRooms.room_no_search == normalized_room_no,
            FacilityRooms.is_deleted == False
            )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Room already exists in this facility"
            )

        # 6️⃣ Random encryption (actual storage)
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "room_id": payload.room_id,
                "room_type": payload.room_type,
                "wing": payload.wing,
                "isolation_room": payload.isolation_room,
                "notes":payload.notes
            }
        )
        
        features_enc = None
        if payload.features:
            features_enc = encrypt_value(
                ce,
                dek_id,
                json.dumps(payload.features.model_dump())
            )
        

       

       # 7️⃣ Save

       

        room_doc = FacilityRooms(
            room_no_search = normalized_room_no,
            room_type_search = normalized_room_type,
            room_number=encrypted["room_id"],
            room_type=encrypted["room_type"],
            wing=encrypted["wing"],
            room_features=features_enc,
            isolation_room=encrypted["isolation_room"],
            notes=encrypted["notes"],
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
    except Exception as e:
        print("❌ Crash:", e)
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


@router.get("/list/")
async def get_facility_rooms(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    try:
        # 1️⃣ User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # 2️⃣ Encryption
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        # ----------------------------
        # 3️⃣ Query conditions (Beanie style)
        # ----------------------------
        conditions = [
            FacilityRooms.created_by.id == user.id,
            FacilityRooms.is_deleted == False
        ]

        if status:
            conditions.append(FacilityRooms.status == status.lower())

        
        if search:
            search_value = search.lower()
            conditions.append(
                Or(
                     RegEx(FacilityRooms.room_no_search, f"^{search_value}"),
                    RegEx(FacilityRooms.facility_id.facility_name_search, f"^{search_value}"),
                    
                )
               
            )

        
        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------

        facility_rooms = await (
            FacilityRooms.find(
                *conditions,
                fetch_links=True
            )
            .sort("-created_at")
            .skip(skip)
            .limit(page_size)
            .to_list()
        )

       

        # ----------------------------
        # 6️⃣ Total count (IMPORTANT)
        # ----------------------------
        total = await FacilityRooms.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------

        result = []
        for rooms in facility_rooms:
            result.append({
                "id": str(rooms.id),
                "room_number": decrypt_value(ce, rooms.room_number),
                "room_type": decrypt_value(ce, rooms.room_type),
                "facility_id": str(rooms.facility_id.id) if rooms.facility_id else None,
                "facility_name": (
                    rooms.facility_id.facility_name_search
                    if rooms.facility_id else None
                ),
                "wings":decrypt_value(ce,rooms.wing),
                "floors":(
                    rooms.floor.floor_label_search
                    if rooms.floor else None
                ),
                
                "rooms_features": (
                    json.loads(decrypt_value(ce, rooms.room_features))
                    if rooms.room_features else None
                ),
                "isolation_rooms":decrypt_value(ce,rooms.isolation_room),
                "notes":decrypt_value(ce,rooms.notes),
                "status": rooms.status,
                "created_at": rooms.created_at,
                "updated_at": rooms.updated_at,
            })
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Facility Rooms",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Rooms fetched | "
                    f"page={page}, page_size={page_size}, "
                    f"search={search}, status={status}, "
                    f"returned={len(result)}"
                ),
            )
        except Exception:
            pass
        return {
            "success": True,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "count": len(result),
            "total": total,
            "data": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")





@router.get("/get/room/{facility_id}/")
async def get_facility_rooms(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    page : int = Query(1, ge=1),
    page_size : int = Query(10, ge=1),
    search: str | None = Query(None, description="Search by room ID or wing"),
):
    # ---------------- User ----------------
    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ---------------- Facility ----------------
    try:
        facility_obj = await Facility.get(PydanticObjectId(facility_id))
    except Exception:
        facility_obj = await Facility.get(facility_id)

    if not facility_obj:
        raise HTTPException(status_code=404, detail="Facility not found")

    # ---------------- Encryption ----------------
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    # ---------------- Rooms (facility + created_by) ----------------
    rooms = await FacilityRooms.find(
        FacilityRooms.facility_id.id == facility_obj.id,
        FacilityRooms.created_by.id == user.id
    ).sort("created_at").to_list()

    # ---------------- Response ----------------
    result = []
    for r in rooms:
        room_id = _decrypt_value(ce, r.room_id)
        wing = _decrypt_value(ce, r.wing)
        if search:
            search_lower = search.lower()
            if (
                search_lower not in str(room_id or "").lower()
                and search_lower not in str(wing or "").lower()
            ):
                continue
        result.append({
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
        })

    total = len(result)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_docs = result[start:end]
    # ---------------- Audit ----------------
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

    return {
        "items": paginated_docs,
        "pagination" : {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": (total + page_size - 1) // page_size,
        }
    }




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
    try:
        current_features = _decrypt_json_field(ce, room_doc.room_features)
    except Exception:
        current_features = None
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
