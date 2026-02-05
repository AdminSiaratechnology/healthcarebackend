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
from beanie.operators import RegEx
from typing import Optional

router = APIRouter(prefix="/category", tags=["Category"])



# @router.post("/create/category/")
# async def create_category(
#     cat: CategorySchema,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id)
# ):
#     try:
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce
#         dek_id = getattr(request.app, "dek_id", None)
#         if dek_id is None:
#             dek_id = ensure_data_key()
#             request.app.dek_id = dek_id

#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         # Check for existing category with the same name (deterministic compare)
#         enc_name_det = encrypt_value_deterministic(ce, dek_id, cat.name)
       
#         existing = await CategoryDoc.find_one({"name": enc_name_det})
        
#         if not existing:
#             cats = await CategoryDoc.find({}).to_list()
#             for c in cats:
#                 if decrypt_value(ce, c.name) == cat.name:
#                     existing = c
#                     break
            
#         if existing:
#             return {"message": "Category already exists", "id": str(existing.id)}

#         enc_name = enc_name_det

#         doc = CategoryDoc(
#             name=enc_name,
#             created_by=user,
#             created_at=datetime.now(timezone.utc),
#             updated_at=datetime.now(timezone.utc),
#         )
#         await doc.insert()

#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Create",
#                 resource="Category",
#                 resource_id=str(doc.id),
#                 status="success",
#                 notes="Category created",
#             )
#         except Exception:
#             pass

#         return {"id": str(doc.id)}
#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(current_user_id),
#                 action="Create",
#                 resource="Category",
#                 resource_id="N/A",
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail="Internal Server Error while creating category")



@router.post("/create/category/")
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



# @router.get("/get/category/")
# async def list_categories(
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id)
# ):
#     ce = getattr(request.app, "client_encryption", None)
#     if ce is None:
#         ce = init_encryption()
#         request.app.client_encryption = ce

#     user = await UserDoc.get(current_user_id)
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     # cats = await CategoryDoc.find({}).to_list()
#     cats = await CategoryDoc.find(
#         CategoryDoc.created_by.id == user.id
#     ).sort("-created_at").to_list()
#     items = []
#     for c in cats:
#         items.append({
#             "id": str(c.id),
#             "name": decrypt_value(ce, c.name),
#             "created_at": c.created_at,
#             "updated_at": c.updated_at,
#         })

#     try:
#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Read",
#             resource="Category",
#             resource_id="list",
#             status="success",
#             notes="Categories listed",
#         )
#     except Exception:
#         pass

#     return items






@router.get("/category/list/")
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
        # 3️⃣ Query conditions (Beanie style)
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

        # --------------------------------------------------
        # 6️⃣ Total count
        # --------------------------------------------------
        total = await CategoryDoc.find(*conditions).count()

        # --------------------------------------------------
        # 7️⃣ Response formatting
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
            })

        # --------------------------------------------------
        # 8️⃣ Audit log (safe)
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
        # 9️⃣ Final response
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



@router.put("/update/category/{category_id}/")
async def update_category(
    category_id: str,
    cat: CategorySchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce
        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        doc = await CategoryDoc.get(PydanticObjectId(category_id))
        if not doc:
            raise HTTPException(status_code=404, detail="Category not found")

        # Check for existing category with the same name (deterministic compare)
        enc_name_det = encrypt_value_deterministic(ce, dek_id, cat.name)
        existing = await CategoryDoc.find_one({"name": enc_name_det, "_id": {"$ne": doc.id}})
        
        if not existing:
            cats = await CategoryDoc.find({}).to_list()
            for c in cats:
                if c.id != doc.id and decrypt_value(ce, c.name) == cat.name:
                    existing = c
                    break
            
        if existing:
            return {"message": "Category with this name already exists", "id": str(existing.id)}

        doc.name = enc_name_det
        doc.updated_at = datetime.now(timezone.utc)
        await doc.save()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Category",
                resource_id=str(doc.id),
                status="success",
                notes="Category updated",
            )
        except Exception:
            pass

        return {"id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Update",
                resource="Category",
                resource_id=category_id,
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while updating category")    





