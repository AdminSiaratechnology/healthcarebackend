from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key, encrypt_value_deterministic,encrypt_dict
from app.utils.audit import log_audit
from app.schemas.clinicalmonitoring.category import CategorySchema
from beanie import PydanticObjectId
import json
import os
from app.clinicalmonitoring.models.category import CategoryDoc
from app.clinicalmonitoring.models.subcategory import SubcategoryDoc
from beanie.operators import RegEx
from typing import Optional
from beanie.operators import And
from beanie.operators import In

router = APIRouter(prefix="/category", tags=["Category"])



@router.post("/create/")
async def create_category(
    
    payload: CategorySchema,
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

        # 4️⃣ Normalize name (VERY IMPORTANT)
        normalized_category_name = payload.name.strip().lower()

        # 5️⃣ Deterministic encryption (duplicate check)
       
        # 6️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        existing = await CategoryDoc.find_one(
            CategoryDoc.created_by.id == user.id,
            CategoryDoc.name_search == normalized_category_name,
            CategoryDoc.is_deleted == False,
            
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Category name already exists"
            )

        
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "category_name": payload.name,
                
            }
        )
        # 8️⃣ Save
        category = CategoryDoc(
            name_search=normalized_category_name,        # 🔎 search
            name=encrypted["category_name"],
            created_by=user,
            status="active",
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await category.insert()

        # 9️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="CREATE",
                resource="category",
                resource_id=str(category.id),
                status="success",
            )
        except Exception:
            pass

        return {
            "success": True,
            "category_id": str(category.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")




# @router.get("/list/")
# async def get_all_categories(
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),

#     page: int = Query(1, ge=1),
#     page_size: int = Query(10, ge=1, le=100),

#     search: Optional[str] = Query(None),
#     status: Optional[str] = Query(None),
# ):
#     try:
#         # --------------------------------------------------
#         # 1️⃣ Current User
#         # --------------------------------------------------
#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         # --------------------------------------------------
#         # 2️⃣ Encryption init
#         # --------------------------------------------------
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce

#         # --------------------------------------------------
#         # 3️⃣ Query conditions (Beanie style)
#         # --------------------------------------------------
#         conditions = [
#             CategoryDoc.created_by.id == user.id,
#             CategoryDoc.is_deleted == False,
#         ]

#         if status:
#             conditions.append(CategoryDoc.status == status.lower())

#         if search:
#             conditions.append(
#                 RegEx(CategoryDoc.name_search, f"^{search.strip().lower()}")
#             )

#         # --------------------------------------------------
#         # 4️⃣ Pagination
#         # --------------------------------------------------
#         skip = (page - 1) * page_size

#         # --------------------------------------------------
#         # 5️⃣ Fetch categories
#         # --------------------------------------------------
#         categories = await (
#             CategoryDoc.find(
#                 *conditions,
#                 fetch_links=True
#             )
#             .sort("-created_at")
#             .skip(skip)
#             .limit(page_size)
#             .to_list()
#         )

#         # --------------------------------------------------
#         # 6️⃣ Total count
#         # --------------------------------------------------
#         total = await CategoryDoc.find(*conditions).count()

#         # --------------------------------------------------
#         # 7️⃣ Response formatting
#         # --------------------------------------------------
#         result = []
#         for category in categories:
#             result.append({
#                 "id": str(category.id),
#                 "name": decrypt_value(ce, category.name),
#                 "status": category.status,
#                 "created_by": (
#                     str(category.created_by.id)
#                     if category.created_by else None
#                 ),
#                 "created_at": category.created_at,
#                 "updated_at": category.updated_at,
#             })

#         # --------------------------------------------------
#         # 8️⃣ Audit log (safe)
#         # --------------------------------------------------
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="READ",
#                 resource="Category",
#                 resource_id="LIST",
#                 status="success",
#                 notes=(
#                     f"Categories fetched | "
#                     f"page={page}, page_size={page_size}, "
#                     f"search={search}, status={status}, "
#                     f"returned={len(result)}"
#                 ),
#             )
#         except Exception:
#             pass

#         # --------------------------------------------------
#         # 9️⃣ Final response
#         # --------------------------------------------------
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
#         print("❌ Category List Crash:", e)
#         raise HTTPException(
#             status_code=500,
#             detail="Internal Server Error while fetching categories",
#         )


@router.get("/list/")
async def get_all_categories(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    try:
        # --------------------------------------------------
        # 1️⃣ Current User
        # --------------------------------------------------
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # --------------------------------------------------
        # 2️⃣ Encryption init
        # --------------------------------------------------
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        # --------------------------------------------------
        # 3️⃣ Category query conditions
        # --------------------------------------------------
        conditions = [
            CategoryDoc.created_by.id == user.id,
            CategoryDoc.is_deleted == False,
        ]

        if status:
            conditions.append(CategoryDoc.status == status.lower())

        if search:
            conditions.append(
                RegEx(CategoryDoc.name_search, f"^{search.strip().lower()}")
            )

        # --------------------------------------------------
        # 4️⃣ Pagination
        # --------------------------------------------------
        skip = (page - 1) * page_size

        # --------------------------------------------------
        # 5️⃣ Fetch categories
        # --------------------------------------------------
        categories = await (
            CategoryDoc.find(
                *conditions,
                fetch_links=True
            )
            .sort("-created_at")
            .skip(skip)
            .limit(page_size)
            .to_list()
        )

        total = await CategoryDoc.find(*conditions).count()

        # --------------------------------------------------
        # 6️⃣ Fetch ALL subcategories (single query)
        # --------------------------------------------------
        category_ids = [cat.id for cat in categories]

        
        subcategories = await SubcategoryDoc.find(
            In(SubcategoryDoc.category_id.id, category_ids),
            SubcategoryDoc.created_by.id == user.id,
            SubcategoryDoc.is_deleted == False,
            fetch_links=True
        ).to_list()
       

        # --------------------------------------------------
        # 7️⃣ Group subcategories by category_id
        # --------------------------------------------------
        subcategory_map: dict[str, list] = {}

        for sub in subcategories:
            cat_id = str(sub.category_id.id)

            subcategory_map.setdefault(cat_id, []).append({
                "id": str(sub.id),
                "name": decrypt_value(ce, sub.name),
                "status": sub.status,
                "created_at": sub.created_at,
                "updated_at": sub.updated_at,
            })

        # --------------------------------------------------
        # 8️⃣ Build final response
        # --------------------------------------------------
        result = []

        for category in categories:
            result.append({
                "id": str(category.id),
                "name": decrypt_value(ce, category.name),
                "status": category.status,
                "created_by": (
                    str(category.created_by.id)
                    if category.created_by else None
                ),
                "created_at": category.created_at,
                "updated_at": category.updated_at,

                # 🔥 Always present (even if empty)
                "subcategories": subcategory_map.get(str(category.id), [])
            })

        # --------------------------------------------------
        # 9️⃣ Audit log
        # --------------------------------------------------
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="READ",
                resource="Category",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Categories fetched | "
                    f"page={page}, page_size={page_size}, "
                    f"search={search}, status={status}, "
                    f"returned={len(result)}"
                ),
            )
        except Exception:
            pass

        # --------------------------------------------------
        # 🔟 Final Response
        # --------------------------------------------------
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
        print("❌ Category List Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while fetching categories",
        )


@router.put("/update/{category_id}/")
async def update_category(
    category_id: str,
    payload: CategorySchema,
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
            category_obj_id = PydanticObjectId(category_id)
            
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Category ID")

        # 4️⃣ Fetch category (Beanie-correct)
       
        category = await CategoryDoc.find_one(
            CategoryDoc.id == category_obj_id,
            CategoryDoc.created_by.id == user.id,
            CategoryDoc.is_deleted == False,
        )
        
        

        if not category:
            raise HTTPException(status_code=404, detail="category not found")

        # 5️⃣ Normalize name
        normalized_name_search = payload.name.strip().lower()

        # 6️⃣ Duplicate validation
        if normalized_name_search != CategoryDoc.name_search:
            duplicate = await CategoryDoc.find_one(
                And(
                    # CategoryDoc.facility_id == campus_block.facility_id,
                    CategoryDoc.name_search == normalized_name_search,
                    CategoryDoc.is_deleted == False,
                    CategoryDoc.id != category.id,
                )
            )

            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="category name already exists ",
                )

        # 7️⃣ Encrypt & update
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "category_name": payload.name,
                
            },
        )

        category.name = encrypted["category_name"]
        category.name_search = normalized_name_search
        category.updated_at = datetime.now(timezone.utc)

        await category.save()

        # Audit log
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Category",
                resource_id=str(category.id),
                status="success",
                notes="Category updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "message": "Category updated successfully",
            "category_id": str(category.id),
            "updated_at": category.updated_at,
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
                resource="Category",
                resource_id=str(category_id),
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error")

