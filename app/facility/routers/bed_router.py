from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File,Query
from pydantic import ValidationError
from typing import Optional

from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value,init_encryption,ensure_data_key,encrypt_dict
from app.utils.audit import log_audit
from app.schemas.facilities.bed import Bed
from beanie import PydanticObjectId
from app.facility.models.beds import Beds
from beanie.operators import In,RegEx,Or



router = APIRouter(prefix="/beds", tags=["Masters"])


@router.post("/create/{facility_id}/")
async def create_bed(
    facility_id: str,
    payload: Bed,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
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
        
        
        
        try:
            room_obj_id = ObjectId(payload.room_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Rooms ID")

        rooms = await FacilityRooms.find_one(
            FacilityRooms.id == room_obj_id,
            FacilityRooms.facility_id.id == facility.id,   # ✅ FIX
            FacilityRooms.is_deleted == False,
        )

        if not rooms:
            raise HTTPException(
                status_code=404,
                detail="Rooms not found in this facility"
            )
        
        # 4️⃣ Normalize name (VERY IMPORTANT)
        normalized_bed_no = payload.bed_number.strip().lower()
        normalized_bed_status = payload.bed_status.strip().lower()

        # 5️⃣Duplicate validation (ACTIVE RECORDS ONLY)

        
        existing = await Beds.find_one(
            Beds.facility_id.id == facility.id,
            Beds.bed_no_search == normalized_bed_no,
            Beds.is_deleted == False
            )
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Beds already exists in this facility"
            )
        
        # 6️⃣ Random encryption (actual storage)
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "bed_number": payload.bed_number,
                "designation": payload.designation,
                "bed_status": payload.bed_status,
                "bariatric": payload.bariatric,
                "move_policyes":payload.move_policy
            }
        )
        

        # 7️⃣ Save
        

       


        

        bed_doc = Beds(
            facility_id=facility,
            room_id = rooms,
            created_by=user,

            bed_number=encrypted["bed_number"],
            
            designation=encrypted["designation"],
            bed_status=encrypted["bed_status"],
            bariatric=encrypted["bariatric"],
            bed_policy=encrypted["move_policyes"],
            bed_no_search = normalized_bed_no,
            bed_status_search = normalized_bed_status
             
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


@router.get("/list/")
async def get_facility_beds(
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
            Beds.created_by.id == user.id,
            Beds.is_deleted == False
        ]

        if status:
            conditions.append(Beds.status == status.lower())

        
        if search:
            search_value = search.lower()
            conditions.append(
                Or(
                    RegEx(Beds.bed_no_search, f"^{search_value}"),
                    RegEx(Beds.facility_id.facility_name_search, f"^{search_value}"),
                    RegEx(Beds.bed_status_search, f"^{search_value}"),
                    
                )
               
            )

        
        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------

        facility_beds = await (
            Beds.find(
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
        total = await Beds.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------

        result = []
        for beds in facility_beds:
            result.append({
                "id": str(beds.id),
                "room_number": (
                    beds.room_id.room_no_search
                    if beds.room_id else None
                ),
                "bed_number": decrypt_value(ce, beds.bed_number),
                "facility_id": str(beds.facility_id.id) if beds.facility_id else None,
                "facility_name": (
                    beds.facility_id.facility_name_search
                    if beds.facility_id else None
                ),
                "designation":decrypt_value(ce,beds.designation),
                "bed_status":decrypt_value(ce,beds.bed_status),
                "bariatric":decrypt_value(ce,beds.bariatric),
                "bed_policy":decrypt_value(ce,beds.bed_policy),
                "floors_name":(
                    beds.room_id.floor_id.floor_label_search
                    if beds.room_id.floor_id else None
                ),
                "status": beds.status,
                "created_at": beds.created_at,
                "updated_at": beds.updated_at,
            })
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Facility Beds",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Beds fetched | "
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





   
    

@router.put("/update/{bed_id}/{facility_id}/")
async def update_facility_bed(
    bed_id: str,
    facility_id : str,
    payload: Bed,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # 1️⃣ User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 2️⃣ Encryption
        ce = getattr(request.app, "client_encryption", None) or init_encryption()
        request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None) or ensure_data_key()
        request.app.dek_id = dek_id

        # 3️⃣ Validate bed id
        try:
            bed_obj_id = PydanticObjectId(bed_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Bed ID")

        # 4️⃣ Fetch bed
        bed = await Beds.find_one(
            Beds.id == bed_obj_id,
            Beds.created_by.id == user.id,
            Beds.is_deleted == False,
        )

        if not bed:
            raise HTTPException(status_code=404, detail="Bed not found")
        
        try:
            facility_obj_id = ObjectId(facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID")
        
        facility = await Facility.find_one(
            Facility.id == facility_obj_id,
            # Facility.is_deleted == False,
            Facility.created_by.id == user.id,
        )

        if not facility:
            raise HTTPException(
                status_code=404,
                detail="Facility not found or access denied",
            )

        bed.facility_id = facility

        # 5️⃣ Validate room (if changed)
        if payload.room_id:
            try:
                room_obj_id = PydanticObjectId(payload.room_id)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid Room ID")

            room = await FacilityRooms.find_one(
                FacilityRooms.id == room_obj_id,
                FacilityRooms.facility_id.id == facility.id,
                FacilityRooms.is_deleted == False,
            )

            if not room:
                raise HTTPException(
                    status_code=404,
                    detail="Room not found in this facility",
                )

            bed.room_id = room

        # 6️⃣ Duplicate bed number check
        if payload.bed_number:
            normalized_bed_no = payload.bed_number.strip().lower()

            if normalized_bed_no != bed.bed_no_search:
                duplicate = await Beds.find_one(
                    Beds.facility_id.id == facility.id,
                    Beds.bed_no_search == normalized_bed_no,
                    Beds.is_deleted == False,
                    Beds.id != bed.id,
                )

                if duplicate:
                    raise HTTPException(
                        status_code=400,
                        detail="Bed number already exists in this facility",
                    )

                bed.bed_no_search = normalized_bed_no
                bed.bed_number = encrypt_value(
                    ce, dek_id, payload.bed_number
                )

        # 7️⃣ Update fields
        if payload.designation is not None:
            bed.designation = encrypt_value(ce, dek_id, payload.designation)

        if payload.bed_status is not None:
            bed.bed_status_search = payload.bed_status.value.lower()
            bed.bed_status = encrypt_value(
                ce, dek_id, payload.bed_status.value
            )

        if payload.bariatric is not None:
            bed.bariatric = encrypt_value(ce, dek_id, payload.bariatric)

        if payload.move_policy is not None:
            bed.bed_policy = encrypt_value(ce, dek_id, payload.move_policy)

        # 8️⃣ Timestamp
        bed.updated_at = datetime.now(timezone.utc)
        await bed.save()

        # ----------------------------
        # 9️⃣ Audit Log (SUCCESS)
        # ----------------------------
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Facility Beds",
                resource_id=str(bed.id),
                status="success",
                notes=(
                    f"Facility Bed updated | "
                    f"bed_id={bed.id}, "
                    
                ),
            )
        except Exception:
            pass

        return {
            "success": True,
            "bed_id": str(bed.id),
            "message": "Bed updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating bed",
        )
