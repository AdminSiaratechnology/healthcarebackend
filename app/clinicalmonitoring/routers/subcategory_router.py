from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import BaseModel, ValidationError
from typing import Optional
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key,encrypt_dict, encrypt_value_deterministic
from app.utils.audit import log_audit
from app.schemas.clinicalmonitoring.subcategory import SubcategorySchema
from beanie import PydanticObjectId
import json
import os
from app.clinicalmonitoring.models.subcategory import SubcategoryDoc
from app.clinicalmonitoring.models.category import CategoryDoc
from bson import ObjectId
from beanie.operators import RegEx
from beanie.operators import And


router = APIRouter(prefix="/subcategory", tags=["Subcategory"])




@router.post("/create/{category_id}/")
async def create_subcategory(
    category_id: str,
    payload: SubcategorySchema,
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
        # facility = await Facility.find_one({
        #     "_id": ObjectId(facility_id),
        #     "created_by.$id": ObjectId(user.id),
        #     # "is_deleted": False
        # })
        # if not facility:
        #     raise HTTPException(status_code=404, detail="Facility not found")

        try:
            category_obj_id = ObjectId(category_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid category Id")

        category = await CategoryDoc.find_one(
            CategoryDoc.id == category_obj_id,
            CategoryDoc.created_by.id == user.id,
            # Facility.is_deleted == False,
        )

        if not category:
            raise HTTPException(status_code=404, detail="category not found")

        # 4️⃣ Normalize name (VERY IMPORTANT)
        normalized_subcategory_name = payload.name.strip().lower()

        # 5️⃣ Deterministic encryption (duplicate check)
       
        # 6️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        existing = await SubcategoryDoc.find_one(
            SubcategoryDoc.created_by.id == user.id,
            SubcategoryDoc.name_search == normalized_subcategory_name,
            SubcategoryDoc.is_deleted == False,
            
        )


        if existing:
            raise HTTPException(
                status_code=400,
                detail="Subcategory name already exists "
            )

        # 7️⃣ Random encryption (actual storage)
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "name": payload.name,
                # "description": payload.description,
                # "content": payload.content,
            }
        )

        if not payload.fields:
            raise HTTPException(status_code=400, detail="Fields are required")

        # 8️⃣ Save
        subcategory = SubcategoryDoc(
            category_id = category,
            name=encrypted["name"],
            # description=encrypted["description"],
            # content=encrypted["content"],
            # fields=[field.dict() for field in payload.fields], 
            field=payload.field.model_dump(exclude_none=True) if payload.field else None,
            name_search=normalized_subcategory_name,        # 🔎 search
            created_by=user,
            status="active",
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await subcategory.insert()

        # 9️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="CREATE",
                resource="subcategory",
                resource_id=str(subcategory.id),
                status="success",
            )
        except Exception:
            pass

        return {
            "success": True,
            "subcategory_id": str(subcategory.id),
            "message" : "Subcategory added successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")




@router.get("/list/")
async def subcategory_list(
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
            # SubcategoryDoc.created_by.id == user.id,
            SubcategoryDoc.is_deleted == False

        ]

        if status:
            conditions.append(SubcategoryDoc.status == status.lower())

        
        if search:
            conditions.append(
                RegEx(SubcategoryDoc.name_search, f"^{search.lower()}")
            )

        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------
        subcategory = await (
            SubcategoryDoc.find(
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
        total = await SubcategoryDoc.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------
        result = []
        for sub_category in subcategory:
            result.append({
                "id": str(sub_category.id),
                "name": decrypt_value(ce, sub_category.name),
                "field": sub_category.field, 
                # "description": decrypt_value(ce, sub_category.description),
                # "content": decrypt_value(ce, sub_category.content),
                "category_id": str(sub_category.category_id.id) if sub_category.category_id else None,
                "category_name": (
                    sub_category.category_id.name_search
                    if sub_category.category_id else None
                ),
                "status": sub_category.status,
                "created_at": sub_category.created_at,
                "updated_at": sub_category.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Subcategory",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Subcategory fetched | "
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




@router.put("/update/{subcategory_id}/")
async def update_subcategory(
    subcategory_id: str,
    payload: SubcategorySchema,
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
            subcategory_obj_id = PydanticObjectId(subcategory_id)
            
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid subcategory ID")

        # 4️⃣ Fetch category (Beanie-correct)
       
        subcategory = await SubcategoryDoc.find_one(
            SubcategoryDoc.id == subcategory_obj_id,
            # SubcategoryDoc.created_by.id == user.id,
            SubcategoryDoc.is_deleted == False,
        )
            

        if not subcategory:
            raise HTTPException(status_code=404, detail="subcategory not found")

        # 5️⃣ Normalize name
        normalized_name_search = payload.name.strip().lower()

        # 6️⃣ Duplicate validation
        # if normalized_name_search != SubcategoryDoc.name_search:
        #     duplicate = await SubcategoryDoc.find_one(
        #         And(
        #             # CategoryDoc.facility_id == campus_block.facility_id,
        #             SubcategoryDoc.name_search == normalized_name_search,
        #             SubcategoryDoc.is_deleted == False,
        #             SubcategoryDoc.id != subcategory.id,
        #         )
        #     )

        #     if duplicate:
        #         raise HTTPException(
        #             status_code=400,
        #             detail="subcategory name already exists ",
        #         )

        if normalized_name_search != subcategory.name_search:
            duplicate = await SubcategoryDoc.find_one(
                And(
                    SubcategoryDoc.name_search == normalized_name_search,
                    SubcategoryDoc.is_deleted == False,
                    SubcategoryDoc.id != subcategory.id,
                )
            )

            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="subcategory name already exists",
                )

        # 7️⃣ Encrypt & update
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "subcategory_name": payload.name,
                # "description": payload.description,
                # "content": payload.content,
                
            },
        )

        subcategory.name = encrypted["subcategory_name"]
        # subcategory.description = encrypted["description"]
        # subcategory.content = encrypted["content"]
        subcategory.name_search = normalized_name_search


        if payload.field is not None:
            subcategory.field = payload.field.model_dump(exclude_none=True)

        subcategory.updated_at = datetime.now(timezone.utc)

        await subcategory.save()

        # Audit log
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="subcategory",
                resource_id=str(subcategory.id),
                status="success",
                notes="subcategory updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "message": "subcategory updated successfully",
            "subcategory_id": str(subcategory.id),
            "updated_at": subcategory.updated_at,
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
                resource="Subcategory",
                resource_id=str(subcategory_id),
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error")

