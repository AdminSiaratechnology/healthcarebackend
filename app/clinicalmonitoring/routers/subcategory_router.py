from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, ValidationError
from typing import Optional
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key, encrypt_value_deterministic
from app.utils.audit import log_audit
from app.schemas.clinicalmonitoring.subcategory import SubcategorySchema
from beanie import PydanticObjectId
import json
import os
from app.clinicalmonitoring.models.subcategory import SubcategoryDoc
from app.clinicalmonitoring.models.category import CategoryDoc


router = APIRouter(prefix="/subcategory", tags=["Subcategory"])


def _dec_str(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode() if isinstance(raw, (bytes, bytearray)) else raw


def _enc_det_or_none(client_encryption, dek_id, value):
    if value is None:
        return None
    return encrypt_value_deterministic(client_encryption, dek_id, value)

class SubcategoryUpdateSchema(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None


@router.post("/create/subcategory/{category_id}/")
async def create_subcategory(
    subcat: SubcategorySchema,
    request: Request,
    category_id: str,
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

        try:
            cat_doc = await CategoryDoc.get(PydanticObjectId(category_id))
        except Exception:
            cat_doc = None
        if not cat_doc:
            raise HTTPException(status_code=404, detail="Category not found")

        enc_name_det = _enc_det_or_none(ce, dek_id, subcat.name)
        enc_description_det = _enc_det_or_none(ce, dek_id, subcat.description)
        enc_content_det = _enc_det_or_none(ce, dek_id, subcat.content)
        existing = await SubcategoryDoc.find_one({"category_id.$id": cat_doc.id, "name": enc_name_det})
        if not existing:
            subs = await SubcategoryDoc.find({"category_id.$id": cat_doc.id}).to_list()
            for s in subs:
                if _dec_str(ce, s.name) == subcat.name:
                    existing = s
                    break
        if existing:
            return {"message": "Subcategory already exists", "id": str(existing.id)}

        doc = SubcategoryDoc(
            category_id=cat_doc,
            name=enc_name_det,
            description=enc_description_det,
            content=enc_content_det,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Subcategory",
                resource_id=str(doc.id),
                status="success",
                notes="Subcategory created",
            )
        except Exception:
            pass

        return {"status":"success","id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Create",
                resource="Subcategory",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while creating subcategory")


@router.get("/get/subcategory/{category_id}/")
async def list_subcategories(
    request: Request,
    category_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        cat_doc = await CategoryDoc.get(PydanticObjectId(category_id))
        
    except Exception:
        cat_doc = None
    if not cat_doc:
        raise HTTPException(status_code=404, detail="Category not found")

    subs = await SubcategoryDoc.find({"category_id.$id": cat_doc.id}).to_list()
    
    items = []
    for s in subs:
        items.append({
            "id": str(s.id),
            "name": _dec_str(ce, s.name),
            "description": _dec_str(ce, s.description),
            "content" : _dec_str(ce, s.content),
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        })

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Subcategory",
            resource_id=str(cat_doc.id),
            status="success",
            notes="Subcategories listed",
        )
    except Exception:
        pass

    return items


@router.put("/update/subcategory/{subcategory_id}/")
async def update_subcategory(
    subcategory_id: str,
    subcat: SubcategoryUpdateSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
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

        try:
            sub_obj_id = PydanticObjectId(subcategory_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Subcategory ID format")

        doc = await SubcategoryDoc.get(sub_obj_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Subcategory not found")

        update_data = subcat.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields provided for update")

        old_name = _dec_str(ce, doc.name)
        old_description = _dec_str(ce, doc.description)
        old_content = _dec_str(ce, doc.content)

        new_name = update_data.get("name", old_name)
        if new_name is None or not str(new_name).strip():
            raise HTTPException(status_code=400, detail="Subcategory name is required")
        new_name = str(new_name).strip()

        new_description = update_data.get("description", old_description)
        new_content = update_data.get("content", old_content)

        if "name" in update_data and old_name != new_name:
            enc_name_det = _enc_det_or_none(ce, dek_id, new_name)
            existing = await SubcategoryDoc.find_one({"category_id.$id": doc.category_id.id, "name": enc_name_det})
            if existing and str(existing.id) != str(doc.id):
                return {"message": "Subcategory already exists", "id": str(existing.id)}

            subs = await SubcategoryDoc.find({"category_id.$id": doc.category_id.id}).to_list()
            for s in subs:
                if str(s.id) == str(doc.id):
                    continue
                if _dec_str(ce, s.name) == new_name:
                    return {"message": "Subcategory already exists", "id": str(s.id)}

        doc.name = _enc_det_or_none(ce, dek_id, new_name)
        doc.description = _enc_det_or_none(ce, dek_id, new_description)
        doc.content = _enc_det_or_none(ce, dek_id, new_content)
        doc.updated_at = datetime.now(timezone.utc)
        await doc.save()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Subcategory",
                resource_id=str(doc.id),
                status="success",
                notes="Subcategory updated",
            )
        except Exception:
            pass

        return {
            "success": True,
            "id": str(doc.id),
            "name": _dec_str(ce, doc.name),
            "description": _dec_str(ce, doc.description),
            "content": _dec_str(ce, doc.content),
            "updated_at": doc.updated_at,
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Update",
                resource="Subcategory",
                resource_id=subcategory_id,
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while updating subcategory")
