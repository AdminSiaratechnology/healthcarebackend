from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key, encrypt_value_deterministic, encrypt_dict
from app.utils.audit import log_audit
from app.schemas.clinicalmonitoring.template_builder import TemplateBuilderSchema, TemplateBuilderUpdateSchema
from beanie import PydanticObjectId, WriteRules
import json
import os
from app.clinicalmonitoring.models.subcategory import SubcategoryDoc
from app.clinicalmonitoring.models.template_builder import TemplateBuilderDoc
from app.clinicalmonitoring.models.category import CategoryDoc
from bson import ObjectId
from typing import Optional, List
from beanie.operators import RegEx,Or,In


router = APIRouter(prefix="/templatebuilder", tags=["TemplateBuilder"])


@router.post("/create/")
async def create_template(
    payload: TemplateBuilderSchema,
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

        # 3️⃣ Validate Subcategories
        sub_category_ids = []
        for sc_id in payload.sub_category_ids:
            try:
                sub_category_ids.append(ObjectId(sc_id))
            except:
                raise HTTPException(status_code=400, detail=f"Invalid subcategory ID: {sc_id}")
        
        # Check if they exist
        # subcategories = await SubcategoryDoc.find({"_id": {"$in": sub_category_ids}}).to_list()
        # Beanie cleaner way:
        subcategories = await SubcategoryDoc.find(
            {"_id": {"$in": sub_category_ids}}
        ).to_list()

        if len(subcategories) != len(sub_category_ids):
             raise HTTPException(status_code=404, detail="One or more subcategories not found")

        # 4️⃣ Normalize name (VERY IMPORTANT)
        normalized_name = payload.template_name.strip().lower()

        # 5️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        existing = await TemplateBuilderDoc.find_one(
            TemplateBuilderDoc.created_by.id == user.id,
            TemplateBuilderDoc.name_search == normalized_name,
            TemplateBuilderDoc.is_deleted == False,
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Template name already exists"
            )

        # 6️⃣ Encrypt data
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "template_name": payload.template_name,
                "short_name": payload.short_name,
                "discipline": payload.discipline,
            }
        )

        # 7️⃣ Save
        template_builder = TemplateBuilderDoc(
            sub_category_ids=subcategories,
            template_name=encrypted["template_name"],
            short_name=encrypted.get("short_name"),
            discipline=encrypted.get("discipline"),
            name_search=normalized_name,
            created_by=user,
            status="active",
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await template_builder.insert(link_rule=WriteRules.WRITE)

        # 8️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="CREATE",
                resource="template_builder",
                resource_id=str(template_builder.id),
                status="success",
            )
        except Exception:
            pass

        return {
            "success": True,
            "template_builder_id": str(template_builder.id),
            "message": "Template created successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")


# @router.get("/get_all/")
# async def get_all_templates(
#     request: Request,
#     skip: int = Query(0, ge=0),
#     limit: int = Query(10, ge=1),
#     name_search: Optional[str] = Query(None),
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         # Encryption init for decryption
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce

#         # Query
#         query = TemplateBuilderDoc.find(
#             TemplateBuilderDoc.is_deleted == False,
#             TemplateBuilderDoc.created_by.id == user.id
#         )

#         # Filter by Category Name Search
#         if name_search:
#             # 1. Find Categories matching the name
#             # categories = await CategoryDoc.find(
#             #     {"name_search": {"$regex": name_search.strip().lower(), "$options": "i"}, "is_deleted": False}
#             # ).to_list()
#             search_value = name_search.strip().lower()
#             categories = await CategoryDoc.find(
#             RegEx(CategoryDoc.name_search, name_search.strip().lower(), options="i"),
#             CategoryDoc.is_deleted == False
#         ).to_list()
            
        
            
#             category_ids = [c.id for c in categories]
            
#             if category_ids:
#                 # 2. Find Subcategories linked to these Categories
#                 subcategories = await SubcategoryDoc.find(
#                     {"category_id.$id": {"$in": category_ids}, "is_deleted": False}
#                 ).to_list()
                
#                 subcategory_ids = [sc.id for sc in subcategories]
                
#                 if subcategory_ids:
#                     # 3. Filter Templates that have these Subcategories
#                     query = query.find({"sub_category_ids.$id": {"$in": subcategory_ids}})
#                 else:
#                     # Categories found but no subcategories -> No templates
#                     return {
#                         "success": True,
#                         "total": 0,
#                         "skip": skip,
#                         "limit": limit,
#                         "data": []
#                     }
#             else:
#                 # No category found matching the name -> No templates
#                 return {
#                     "success": True,
#                     "total": 0,
#                     "skip": skip,
#                     "limit": limit,
#                     "data": []
#                 }

#         total_count = await query.count()
#         templates = await query.skip(skip).limit(limit).to_list()
        
#         # Need to fetch links manually or ensure fetch_links=True if needed for deeper access, 
#         # but Beanie handles list[Link] fetching when accessed if fetched with fetch_links=True
#         # Let's refetch with links to be sure
        
#         # Use the IDs from the paginated result to fetch with links
#         # This is more efficient than re-running the complex query if possible, 
#         # but re-running with fetch_links=True is safer to ensure we get the exact same set
        
#         # We need to apply the same query filters to the second fetch
#         # Beanie's query object is mutable/chainable, so 'query' variable has the filters
#         # But we already executed it with .to_list(). 
#         # We can re-use the 'query' object (it maintains state) or rebuild it.
#         # Actually Beanie query objects can be cloned or re-executed.
#         # But simpler: just use the IDs we got to fetch details
        
#         template_ids = [t.id for t in templates]
#         templates_with_links = await TemplateBuilderDoc.find(
#             {"_id": {"$in": template_ids}},
#             fetch_links=True
#         ).to_list()
        
#         # Maintain order is not guaranteed with $in, but usually okay for display. 
#         # If strict order needed, we'd map back.

#         result = []
#         for t in templates_with_links:
#             # Decrypt
#             decrypted_data = {
#                 "id": str(t.id),
#                 "template_name": decrypt_value(ce, t.template_name) if t.template_name else None,
#                 "short_name": decrypt_value(ce, t.short_name) if t.short_name else None,
#                 "discipline": decrypt_value(ce, t.discipline) if t.discipline else None,
#                 "created_at": t.created_at,
#                 "updated_at": t.updated_at,
#                 "status": t.status,
#                 "sub_categories": []
#             }

#             # Handle subcategories
#             if t.sub_category_ids:
#                 for sc in t.sub_category_ids:
#                     # sc is a Link or the document if fetched
#                     # Since we used fetch_links=True, it should be the document or Link with populated doc
#                     # Beanie's behavior with List[Link] and fetch_links=True populates the list with documents
#                     if isinstance(sc, SubcategoryDoc):
#                          decrypted_data["sub_categories"].append({
#                             "id": str(sc.id),
#                             "name": decrypt_value(ce, sc.name) if sc.name else None,
#                             "description": decrypt_value(ce, sc.description) if sc.description else None,
#                             "content": decrypt_value(ce, sc.content) if sc.content else None,
#                         })
#                     elif hasattr(sc, "ref") and sc.ref: # It's a Link with populated ref? Beanie list[Link] is tricky
#                         # Actually if fetch_links=True, list items are the documents.
#                         pass
                    
#             result.append(decrypted_data)

#         return {
#             "success": True,
#             "total": total_count,
#             "skip": skip,
#             "limit": limit,
#             "data": result
#         }

#     except Exception as e:
#         print("❌ Crash:", e)
#         raise HTTPException(status_code=500, detail="Internal Server Error")





@router.get("/get_all/")
async def get_all_templates(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1),
    name_search: Optional[str] = Query(None),
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # 🔹 1️⃣ Get User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 🔹 2️⃣ Encryption Init
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        # 🔹 3️⃣ Base Filters
        base_filters = [
            TemplateBuilderDoc.is_deleted == False,
            TemplateBuilderDoc.created_by.id == user.id
        ]

        # 🔹 4️⃣ Search Logic
        if name_search:
            search_value = name_search.strip().lower()

            # 4️⃣.1 Category search
            categories = await CategoryDoc.find(
                CategoryDoc.is_deleted == False,
                RegEx(CategoryDoc.name_search, search_value, options="i")
            ).to_list()

            category_ids = [c.id for c in categories]

            subcategory_ids = []

            if category_ids:
                subcategories = await SubcategoryDoc.find(
                    SubcategoryDoc.is_deleted == False,
                    In(SubcategoryDoc.category_id.id, category_ids)
                ).to_list()

                subcategory_ids = [sc.id for sc in subcategories]

            # 4️⃣.2 Build OR conditions
            or_conditions = [
                RegEx(TemplateBuilderDoc.name_search, search_value, options="i")
            ]

            if subcategory_ids:
                or_conditions.append(
                    In(TemplateBuilderDoc.sub_category_ids.id, subcategory_ids)
                )

            query = TemplateBuilderDoc.find(
                *base_filters,
                Or(*or_conditions)
            )

        else:
            query = TemplateBuilderDoc.find(*base_filters)

        # 🔹 5️⃣ Count
        total_count = await query.count()

        # 🔹 6️⃣ Fetch paginated IDs first
        templates = await query.skip(skip).limit(limit).to_list()

        template_ids = [t.id for t in templates]

        if not template_ids:
            return {
                "success": True,
                "total": 0,
                "skip": skip,
                "limit": limit,
                "data": []
            }

        # 🔹 7️⃣ Fetch with links
        templates_with_links = await TemplateBuilderDoc.find(
            In(TemplateBuilderDoc.id, template_ids),
            fetch_links=True
        ).to_list()

        # 🔹 8️⃣ Maintain Order
        template_map = {t.id: t for t in templates_with_links}
        ordered_templates = [template_map[t_id] for t_id in template_ids if t_id in template_map]

        # 🔹 9️⃣ Prepare Response
        result = []

        for t in ordered_templates:
            data = {
                "id": str(t.id),
                "template_name": decrypt_value(ce, t.template_name) if t.template_name else None,
                "short_name": decrypt_value(ce, t.short_name) if t.short_name else None,
                "discipline": decrypt_value(ce, t.discipline) if t.discipline else None,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
                "status": t.status,
                "sub_categories": []
            }

            if t.sub_category_ids:
                for sc in t.sub_category_ids:
                    data["sub_categories"].append({
                        "id": str(sc.id),
                        "name": decrypt_value(ce, sc.name) if sc.name else None,
                        "description": decrypt_value(ce, sc.description) if sc.description else None,
                        "content": decrypt_value(ce, sc.content) if sc.content else None,
                    })

            result.append(data)

        return {
            "success": True,
            "total": total_count,
            "skip": skip,
            "limit": limit,
            "data": result
        }

    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.put("/update/{template_id}")
async def update_template(
    template_id: str,
    payload: TemplateBuilderUpdateSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        # Find existing
        template = await TemplateBuilderDoc.find_one(
            TemplateBuilderDoc.id == ObjectId(template_id),
            TemplateBuilderDoc.created_by.id == user.id,
            TemplateBuilderDoc.is_deleted == False
        )

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # Prepare update dict
        update_data = {}
        
        # Handle Subcategories update
        if payload.sub_category_ids is not None:
            sub_category_ids = []
            for sc_id in payload.sub_category_ids:
                try:
                    sub_category_ids.append(ObjectId(sc_id))
                except:
                    raise HTTPException(status_code=400, detail=f"Invalid subcategory ID: {sc_id}")
            
            subcategories = await SubcategoryDoc.find(
                {"_id": {"$in": sub_category_ids}}
            ).to_list()
            
            if len(subcategories) != len(sub_category_ids):
                 raise HTTPException(status_code=404, detail="One or more subcategories not found")
            
            template.sub_category_ids = subcategories

        # Prepare for encryption
        data_to_encrypt = {}
        if payload.template_name is not None:
            data_to_encrypt["template_name"] = payload.template_name
            # Update search field
            template.name_search = payload.template_name.strip().lower()
            
            # Check duplicate name if name changed
            existing_name = await TemplateBuilderDoc.find_one(
                TemplateBuilderDoc.created_by.id == user.id,
                TemplateBuilderDoc.name_search == template.name_search,
                TemplateBuilderDoc.is_deleted == False,
                TemplateBuilderDoc.id != template.id 
            )
            if existing_name:
                 raise HTTPException(status_code=400, detail="Template name already exists")

        if payload.short_name is not None:
            data_to_encrypt["short_name"] = payload.short_name
        
        if payload.discipline is not None:
            data_to_encrypt["discipline"] = payload.discipline

        if data_to_encrypt:
            encrypted = encrypt_dict(ce, dek_id, data_to_encrypt)
            
            if "template_name" in encrypted:
                template.template_name = encrypted["template_name"]
            if "short_name" in encrypted:
                template.short_name = encrypted["short_name"]
            if "discipline" in encrypted:
                template.discipline = encrypted["discipline"]

        template.updated_at = datetime.now(timezone.utc)
        await template.save()

        # Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="UPDATE",
                resource="template_builder",
                resource_id=str(template.id),
                status="success",
            )
        except Exception:
            pass

        return {
            "success": True,
            "template_builder_id": str(template.id),
            "message": "Template updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")
