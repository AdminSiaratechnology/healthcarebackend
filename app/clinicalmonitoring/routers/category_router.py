from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key, encrypt_value_deterministic
from app.utils.audit import log_audit
from app.schemas.clinicalmonitoring.category import CategorySchema
from beanie import PydanticObjectId
import json
import os
from app.clinicalmonitoring.models.category import CategoryDoc


router = APIRouter(prefix="/category", tags=["Category"])


def _dec_str(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode() if isinstance(raw, (bytes, bytearray)) else raw


@router.post("/create/category/")
async def create_category(
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

        # Check for existing category with the same name (deterministic compare)
        enc_name_det = encrypt_value_deterministic(ce, dek_id, cat.name)
        existing = await CategoryDoc.find_one({"name": enc_name_det})
        
        if not existing:
            cats = await CategoryDoc.find({}).to_list()
            for c in cats:
                if _dec_str(ce, c.name) == cat.name:
                    existing = c
                    break
            
        if existing:
            return {"message": "Category already exists", "id": str(existing.id)}

        enc_name = enc_name_det

        doc = CategoryDoc(
            name=enc_name,
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
                resource="Category",
                resource_id=str(doc.id),
                status="success",
                notes="Category created",
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
                action="Create",
                resource="Category",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while creating category")


@router.get("/get/category/")
async def list_categories(
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # cats = await CategoryDoc.find({}).to_list()
    cats = await CategoryDoc.find(
        CategoryDoc.created_by.id == user.id
    ).sort("-created_at").to_list()
    items = []
    for c in cats:
        items.append({
            "id": str(c.id),
            "name": _dec_str(ce, c.name),
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        })

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Category",
            resource_id="list",
            status="success",
            notes="Categories listed",
        )
    except Exception:
        pass

    return items
