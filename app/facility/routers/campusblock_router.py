from datetime import datetime, timezone
from app.accounts.models.user import UserDoc
from app.facility.models.facility import Facility
from fastapi import APIRouter, Request, HTTPException, Depends,Query
from app.facility.models.campusblock import CampusBlock
from app.schemas.facilities.campus_block import CampusBlockSchema
from app.encryption.encryption import encrypt_dict, encrypt_value, decrypt_value, init_encryption, ensure_data_key,encrypt_value_deterministic
import json
from app.auth.deps import get_current_user_id
from app.utils.audit import log_audit
from bson import ObjectId
from typing import Annotated, Optional

router = APIRouter(prefix="/facility", tags=["Facility"])



@router.post("/create/campusblock/{facility_id}/")
async def create_campus_block(
    facility_id: str,
    payload: CampusBlockSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
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

        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        # 3️⃣ Facility ownership check
        facility = await Facility.find_one({
            "_id": ObjectId(facility_id),
            "created_by.$id": ObjectId(user.id)
        })
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        # 4️⃣ Deterministic encryption (FOR UNIQUE CHECK)
       
        enc_block_name_det = encrypt_value_deterministic(ce, dek_id, payload.block_name)
        

        

       

        existing = await CampusBlock.find_one({
            "block_name_det": enc_block_name_det,
            "facility_id.$id": facility.id
        })
       

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Campus block with the same name already exists"
            )

        # 5️⃣ Random encryption (FOR STORAGE)
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "block_code": payload.block_code,
                "block_name": payload.block_name,
            }
        )

        # 6️⃣ Save
        campus_block = CampusBlock(
            block_name_det = enc_block_name_det,
            block_code=encrypted["block_code"],
            block_name=encrypted["block_name"],
            facility_id=facility,   # ✅ Link object
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await campus_block.insert()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Campus Block",
                resource_id=str(campus_block.id),
                status="success",
            )
        except Exception:
            pass

        return {
            "success": True,
            "campus_block_id": str(campus_block.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")



@router.get("/get/campusblock/{facility_id}/")
async def get_campus_blocks(
    facility_id: str,
    request : Request,
    current_user_id: str = Depends(get_current_user_id),

    # 🔹 pagination
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    # 🔹 filters
    search: Optional[str] = Query(None),


):
    try:
        # ----------------------------
        # 1️⃣ Fetch current user
        # ----------------------------
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # ----------------------------
        # 2️⃣ Encryption
        # ----------------------------
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        
        # ✅ ✅ FIXED FACILITY ID
        try:
            facility_obj_id = ObjectId(facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")

        facilityid = await Facility.get(facility_obj_id)
        if not facilityid:
            raise HTTPException(status_code=404, detail="Facility not found")

        # ----------------------------
        # 3️⃣ Base query (user scope)
        # ----------------------------
        base_query = {
            "created_by.$id": ObjectId(user.id)
        }

        # ----------------------------
        # 4️⃣ Build filtered query
        # ----------------------------
        query = base_query.copy()

        if search:
            enc_name = encrypt_value_deterministic(
                ce,
                request.app.dek_id,
                search
            )
            query["block_name_det"] = enc_name
        # ----------------------------
        # 5️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        campus_block = (
            await CampusBlock.find(query)
            .sort("-created_at")
            .skip(skip)
            .limit(page_size)
            .to_list()
        )

        # ----------------------------
        # 7️⃣ Decrypt response
        # ----------------------------
        result = []
        for cb in campus_block:
           
            result.append({
                "id": str(cb.id),
                "block_name": decrypt_value(ce, cb.block_name),
                "block_code": decrypt_value(ce, cb.block_code),
                "created_at": cb.created_at,
                "updated_at": cb.updated_at
            })
         # ----------------------------
        # 8️⃣ Final response
        # ----------------------------
        return {
            "page": page,
            "page_size": page_size,
            "count": len(result),
            "data": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# @router.put("/update/campusblock/{campus_block_id}/")
# async def update_campus_block(
#     campus_block_id: str,
#     campus_block: CampusBlockSchema,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     client_encryption = getattr(request.app, "client_encryption", None)
#     if client_encryption is None:
#         client_encryption = init_encryption()
#         request.app.client_encryption = client_encryption
#     dek_id = getattr(request.app, "dek_id", None)
#     if dek_id is None:
#         dek_id = ensure_data_key()
#         request.app.dek_id = dek_id

#     def enc_or_none(val):
#         return encrypt_value(client_encryption, dek_id, val) if val is not None else None

#     user = await UserDoc.get(current_user_id)
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     try:
#         from beanie import PydanticObjectId
#         cb_obj_id = PydanticObjectId(campus_block_id)
#     except Exception:
#         raise HTTPException(status_code=400, detail="Invalid Campus Block ID format")

#     cb = await CampusBlock.get(cb_obj_id)
#     if not cb:
#         raise HTTPException(status_code=404, detail="Campus block not found")

#     update_data = campus_block.model_dump(exclude_unset=True, exclude_none=True)
#     if not update_data:
#         raise HTTPException(status_code=400, detail="No fields provided for update")

#     current_code, current_name = _extract_block_values(client_encryption, cb)
#     new_code = update_data.get("block_code", current_code)
#     new_name = update_data.get("block_name", current_name)

#     cb.block_code = enc_or_none(new_code)
#     cb.block_name = enc_or_none(new_name)
#     cb.updated_at = datetime.now(timezone.utc)
#     await cb.save()

#     try:
#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Update",
#             resource="Facility Campus Block",
#             resource_id=str(cb.id),
#             status="success",
#             notes="Facility campus block updated successfully",
#         )
#     except Exception:
#         pass

#     return {
#         "success": True,
#         "campus_block_id": str(cb.id),
#         "updated": {
#             "block_code": new_code,
#             "block_name": new_name,
#         },
#         "updated_at": cb.updated_at,
#     }
