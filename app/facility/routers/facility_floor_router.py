from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File,Query
from pydantic import ValidationError
# from app.schemas.facility import FacilityPayload

from app.facility.models.facility import Facility
from app.facility.models.facility_floor import FacilityFloor

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value,encrypt_dict
# from app.facility.routers.campusblock_router import _extract_block_values
from app.utils.audit import log_audit
from app.schemas.facilities.floor import FloorSchema
from beanie import PydanticObjectId
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key, encrypt_value_deterministic
import json
import os
from typing import Optional
from beanie.operators import RegEx
from beanie.operators import And

router = APIRouter(prefix="/floors", tags=["Masters"])


def _dec_str(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode() if isinstance(raw, (bytes, bytearray)) else raw



from bson import ObjectId

@router.post("/create/{facility_id}/")
async def create_facility_floor(
    facility_id: str,
    payload: FloorSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:

        # 1️⃣ User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
       
        # client_encryption = request.app.client_encryption
        ce = getattr(request.app, "client_encryption", None)

        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None)

        # ✅ Encrypt Body
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id
        
        # ✅ ✅ FIXED FACILITY ID

        # 3️⃣ Facility ownership check
       
        try:
            facility_obj_id = ObjectId(facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")
        

        # 3️⃣ Facility ownership check
        facility = await Facility.find_one({
            "_id":  ObjectId(facility_id),
            "created_by.$id": ObjectId(user.id),
            # "is_deleted": False
        })

        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")
        

        # ✅ Check User

        # 4️⃣ Normalize name (VERY IMPORTANT)
        normalized_floor_label = payload.floor_label.strip().lower()

        # 6️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        existing = await FacilityFloor.find_one({
            "facility_id.$id": facility.id,
            "floor_label_search": normalized_floor_label,
            # "is_deleted": False
        })

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Floor label with this name already exists in this facility"
            )

        # 7️⃣ Random encryption (actual storage)
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "floor_label": payload.floor_label,
                "display": payload.display,
            }
        )
       
        # ✅ Create Floor
        facility_floor_doc = FacilityFloor(
            floor_label_search = normalized_floor_label,
            floor_label=encrypted["floor_label"],
            display=encrypted["display"],
            facility_id=facility,
            created_by=user,
            status="active",
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await facility_floor_doc.insert()

        # ✅ Audit Log
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Facility Floor",
                resource_id=str(facility_floor_doc.id),
                status="success",
                notes="Facility floor created successfully",
            )
        except Exception as audit_error:
            print("⚠️ Audit Log Failed:", audit_error)

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "facility_floor_id": str(facility_floor_doc.id),
            
        }

    except HTTPException:
        raise

    except Exception as e:
        print("❌ Facility Floor Create Crash:", repr(e))
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility floor"
        )


# @router.get('/list/')
# async def get_all_facilities_floors(
#     request : Request,
#     current_user_id: str = Depends(get_current_user_id),
#     page: int = Query(1, ge=1),
#     page_size: int = Query(10, ge=1, le=100),

#     search: Optional[str] = Query(None),
#     status: Optional[str] = Query(None),
# ):
#     try:
#         # 1️⃣ User
#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         # 2️⃣ Encryption
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce

#         # ----------------------------
#         # 3️⃣ Query conditions (Beanie style)
#         # ----------------------------
#         conditions = [
#             FacilityFloor.created_by.id == user.id,
#             FacilityFloor.is_deleted == False,
#         ]

#         if status:
#             conditions.append(FacilityFloor.status == status.lower())

        
#         if search:
#             conditions.append(
#                 RegEx(FacilityFloor.floor_label_search, search.lower())
#             )

#         # ----------------------------
#         # 4️⃣ Pagination
#         # ----------------------------
#         skip = (page - 1) * page_size

#         # ----------------------------
#         # 5️⃣ Fetch data
#         # ----------------------------
#         facility_floors = await (
#             FacilityFloor.find(
#                 *conditions,
#                 fetch_links=True
#             )
#             .sort("-created_at")
#             .skip(skip)
#             .limit(page_size)
#             .to_list()
#         )

#         print("facilitiessss florrr hereeeeeeeeeeee",facility_floors)

#         # ----------------------------
#         # 6️⃣ Total count (IMPORTANT)
#         # ----------------------------
#         total = await FacilityFloor.find(*conditions).count()

#         # ----------------------------
#         # 7️⃣ Response
#         # ----------------------------
#         result = []
#         for floor in facility_floors:
#             result.append({
#                 "id": str(floor.id),
#                 "floor_label": decrypt_value(ce, floor.floor_label),
#                 "floor_display": decrypt_value(ce, floor.display),
#                 "facility_id": str(floor.facility_id.id) if floor.facility_id else None,
#                 "facility_name": (
#                     floor.facility_id.facility_name_search
#                     if floor.facility_id else None
#                 ),
#                 "status": floor.status,
#                 "created_at": floor.created_at,
#                 "updated_at": floor.updated_at,
#             })

#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Read",
#                 resource="Facility Floors",
#                 resource_id="LIST",
#                 status="success",
#                 notes=(
#                     f"Facility Floors fetched | "
#                     f"page={page}, page_size={page_size}, "
#                     f"search={search}, status={status}, "
#                     f"returned={len(result)}"
#                 ),
#             )
#         except Exception:
#             pass
#         return {
#             "success": True,
#             "page": page,
#             "page_size": page_size,
#             "total_pages": (total + page_size - 1) // page_size,
#             "count": len(result),
#             "total": total,
#             "data": result,
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         print("❌ Crash:", e)
#         raise HTTPException(status_code=500, detail="Internal Server Error")




@router.get("/list/")
async def get_all_facilities_floors(
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
        ce = getattr(request.app, "client_encryption", None) or init_encryption()
        request.app.client_encryption = ce

        # 3️⃣ Conditions
        conditions = [
            FacilityFloor.created_by.id == user.id,
            FacilityFloor.is_deleted == False,
        ]

        if status:
            conditions.append(FacilityFloor.status == status.lower())

        if search:
            conditions.append(
                RegEx(FacilityFloor.floor_label_search, search.lower())
            )

        # 4️⃣ Pagination
        skip = (page - 1) * page_size

        # 5️⃣ Data
        floors = (
            await FacilityFloor.find(*conditions, fetch_links=True)
            .sort("-created_at")
            .skip(skip)
            .limit(page_size)
            .to_list()
        )

        # 6️⃣ Count
        total = await FacilityFloor.find(*conditions).count()

        # 7️⃣ Response
        data = []
        for floor in floors:
            data.append({
                "id": str(floor.id),
                "floor_label": decrypt_value(ce, floor.floor_label),
                "floor_display": decrypt_value(ce, floor.display),
                "facility_id": str(floor.facility_id.id) if floor.facility_id else None,
                "facility_name": (
                    floor.facility_id.facility_name_search
                    if floor.facility_id else None
                ),
                "status": floor.status,
                "created_at": floor.created_at,
                "updated_at": floor.updated_at,
            })

        return {
            "success": True,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "count": len(data),
            "total": total,
            "data": data,
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")






# @router.get("/get/floor/{facility_id}/")
# async def get_facility_floors(
#     facility_id: str,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
#     page: int = Query(1, ge=1),
#     page_size: int = Query(10, ge=1),
#     search: str | None = Query(None, description="Search by floor label or display"),
# ):
#     ce = getattr(request.app, "client_encryption", None)
#     if ce is None:
#         ce = init_encryption()
#         request.app.client_encryption = ce
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
    
#     # floor = await FacilityFloor.find({"facility_id.$id": facility_obj.id}).to_list()
#     floor = await FacilityFloor.find(
#     FacilityFloor.facility_id.id == facility_obj.id,
#     FacilityFloor.created_by.id == user.id
#     ).to_list()
#     search_lower = search.lower() if search else None

    
#     items = []
#     for f in floor:
#         floor_label = _dec_str(ce, f.floor_label)
#         display = _dec_str(ce, f.display)
#         # 🔎 Search logic
#         if search_lower:
#             if (
#                 search_lower not in str(floor_label or "").lower()
#                 and search_lower not in str(display or "").lower()
#             ):
#                 continue

#         items.append({
#             "id": str(f.id),
#             "floor_label":_dec_str(ce, f.floor_label),
#             "display":_dec_str(ce, f.display),
#         })
#     total = len(items)
#     start = (page - 1) * page_size
#     end = start + page_size
#     paginated_docs = items[start:end]

  
    

#     try:
#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Read",
#             resource="Facility Floor",
#             resource_id=str(facility_obj.id),
#             status="success",
#             notes="Facility floors fetched successfully",
#         )
#     except Exception:
#         pass

#     return {
#         "items": paginated_docs,
#         "pagination" : {
#             "page": page,
#             "page_size": page_size,
#             "total_items": total,
#             "total_pages": (total + page_size - 1) // page_size,
#         }
#     }


@router.put("/update/{floor_id}/")
async def update_floor(
    floor_id: str,
    payload: FloorSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    # Get user
    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")


    # Encryption setup
    ce = getattr(request.app, "client_encryption", None)

    if ce is None:
        client_encryption = init_encryption()
        request.app.client_encryption = ce

    dek_id = getattr(request.app, "dek_id", None)
    if dek_id is None:
        dek_id = ensure_data_key()
        request.app.dek_id = dek_id

    
    # Validate floor ID
    try:
        floor_obj_id = PydanticObjectId(floor_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Floor ID format")

    # Fetch floor
   
    floors = await FacilityFloor.find_one(
            FacilityFloor.id == floor_obj_id,
            FacilityFloor.created_by.id == user.id,
            FacilityFloor.is_deleted == False,
        )
    if not floors:
        raise HTTPException(status_code=404, detail="Floor Label not found")
    
    

    # 5️⃣ Normalize name


    normalized_floor_label = payload.floor_label.strip().lower()
    # 6️⃣ Duplicate validation

    if normalized_floor_label != floors.floor_label_search:

        duplicate = await FacilityFloor.find_one(
            And(
                FacilityFloor.facility_id == floors.facility_id,
                FacilityFloor.floor_label_search == normalized_floor_label,
                FacilityFloor.is_deleted == False,
                FacilityFloor.id != floors.id,
            )
        )
        if duplicate:
            raise HTTPException(
                status_code=400,
                detail="Facility Floors  with this name already exists in this facility",
            )

    try:


        
        # 7️⃣ Encrypt & update
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "floor_label": payload.floor_label,
                "display": payload.display,
            },
        )

        floors.floor_label = encrypted["floor_label"]
        floors.display = encrypted["display"]
        floors.floor_label_search = normalized_floor_label
        floors.updated_at = datetime.now(timezone.utc)

        
        await floors.save()

        # Audit log
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Facility Floor",
                resource_id=str(floors.id),
                status="success",
                notes="Floor updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "id": str(floors.id),
            # "floor_label": floors.floor_label,
            # "display": floors.display,
            "updated_at": floors.updated_at,
        }

    except HTTPException:
        raise

    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Update",
                resource="Facility Floor",
                resource_id=str(floor_id),
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass

        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating floor",
        )
