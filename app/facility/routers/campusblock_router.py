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
from beanie import PydanticObjectId
from beanie.operators import RegEx,Or
from beanie.operators import And


router = APIRouter(prefix="/campusblock", tags=["Masters"])

@router.post("/create/{facility_id}/")
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
        facility = await Facility.find_one({
            "_id": ObjectId(facility_id),
            "created_by.$id": ObjectId(user.id),
            # "is_deleted": False
        })
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        # 4️⃣ Normalize name (VERY IMPORTANT)
        normalized_block_name = payload.block_name.strip().lower()

        # 5️⃣ Deterministic encryption (duplicate check)
       
        # 6️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        existing = await CampusBlock.find_one({
            "facility_id.$id": facility.id,
            "block_name_search": normalized_block_name,
            # "is_deleted": False
        })

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Campus block with this name already exists in this facility"
            )

        # 7️⃣ Random encryption (actual storage)
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "department_code": payload.block_code,
                "block_name": payload.block_name,
            }
        )

        # 8️⃣ Save
        campus_block = CampusBlock(
            block_name_search=normalized_block_name,        # 🔎 search
            block_code=encrypted["block_code"],
            block_name=encrypted["block_name"],
            facility_id=facility,
            created_by=user,
            status="active",
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await campus_block.insert()

        # 9️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="CREATE",
                resource="campus_block",
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





@router.get("/list/")
async def get_all_campus_blocks(
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
            CampusBlock.created_by.id == user.id,
            CampusBlock.is_deleted == False
        ]

        if status:
            conditions.append(CampusBlock.status == status.lower())

        
        if search:
            conditions.append(
                RegEx(CampusBlock.block_name_search, f"^{search.lower()}")
            )

        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------
        campus_blocks = await (
            CampusBlock.find(
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
        total = await CampusBlock.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------
        result = []
        for block in campus_blocks:
            result.append({
                "id": str(block.id),
                "block_name": decrypt_value(ce, block.block_name),
                "block_code": decrypt_value(ce, block.block_code),
                "facility_id": str(block.facility_id.id) if block.facility_id else None,
                "facility_name": (
                    block.facility_id.facility_name_search
                    if block.facility_id else None
                ),
                "status": block.status,
                "created_at": block.created_at,
                "updated_at": block.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Facility Campus Block",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Campus blocks fetched | "
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



@router.put("/update/{block_id}/{facility_id}/")
async def update_campus_block(
    block_id: str,
    facility_id : str,
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
        ce = getattr(request.app, "client_encryption", None) or init_encryption()
        request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None) or ensure_data_key()
        request.app.dek_id = dek_id

        # 3️⃣ Validate ID
        try:
            block_obj_id = PydanticObjectId(block_id)
            
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Campus Block ID")

        # 4️⃣ Fetch block (Beanie-correct)

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
        

       
        campus_block = await CampusBlock.find_one(
            CampusBlock.id == block_obj_id,
            CampusBlock.created_by.id == user.id,
            CampusBlock.facility_id.id == facility.id,
            CampusBlock.is_deleted == False,
        )

        
        

        

        if not campus_block:
            raise HTTPException(status_code=404, detail="Campus block not found")
        
               

        # 5️⃣ Normalize name
        normalized_block_name = payload.block_name.strip().lower()

        # 6️⃣ Duplicate validation
        if normalized_block_name != campus_block.block_name_search:
            duplicate = await CampusBlock.find_one(
                And(
                    CampusBlock.facility_id == campus_block.facility_id,
                    CampusBlock.block_name_search == normalized_block_name,
                    CampusBlock.is_deleted == False,
                    CampusBlock.id != campus_block.id,
                )
            )

            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="Campus block with this name already exists in this facility",
                )

        # 7️⃣ Encrypt & update
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "block_code": payload.block_code,
                "block_name": payload.block_name,
            },
        )

        campus_block.block_code = encrypted["block_code"]
        campus_block.block_name = encrypted["block_name"]
        campus_block.block_name_search = normalized_block_name
        campus_block.facility_id = facility
        campus_block.updated_at = datetime.now(timezone.utc)

        await campus_block.save()

        # Audit log
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Campus Block",
                resource_id=str(campus_block.id),
                status="success",
                notes="Floor updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "campus_block_id": str(campus_block.id),
            "updated_at": campus_block.updated_at,
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Update",
                resource="Facility Floor",
                resource_id=str(block_id),
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error")

