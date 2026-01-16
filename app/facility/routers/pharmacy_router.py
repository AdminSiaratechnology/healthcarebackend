from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id

from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.pharmacies import PharmaciesSchema
from beanie import PydanticObjectId

import json
import os
from app.facility.models.pharmacies import Pharmacies

router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/pharmacy/{facility_id}/")
async def create_pharmacy(
    facility_id: str,
    pharmacy: PharmaciesSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        client_encryption = request.app.client_encryption
        dek_id = request.app.dek_id

        def enc_or_none(val):
            return encrypt_value(client_encryption, dek_id, val) if val is not None else None

        try:
            facility_obj_id = PydanticObjectId(facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")

        facility = await Facility.get(facility_obj_id)
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        pharmacy_doc = Pharmacies(
            facility_id=facility,
            pharmacy_name=enc_or_none(pharmacy.pharmacy_name),
            phone=enc_or_none(pharmacy.phone),
            address=enc_or_none(pharmacy.address),
            fax=enc_or_none(pharmacy.fax),
            after_hours_phone=enc_or_none(pharmacy.after_hours_phone),
            contract_file_id=enc_or_none(pharmacy.contract_file_id),
            delivery_schedule=enc_or_none(pharmacy.delivery_schedule),
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await pharmacy_doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Pharmacy",
                resource_id=str(pharmacy_doc.id),
                status="success",
                notes="Pharmacy created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "pharmacy_id": str(pharmacy_doc.id),
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating pharmacy"
        )


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return decrypted_raw


@router.get("/get/pharmacy/{facility_id}/")
async def get_pharmacies(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1),
    search: str | None = Query(None, description="Search by pharmacy name or address"),
):
    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    facility_obj = None
    try:
        facility_obj_id = PydanticObjectId(facility_id)
        facility_obj = await Facility.get(facility_obj_id)
    except Exception:
        pass

    if facility_obj is None:
        facility_obj = await Facility.get(facility_id)
    if not facility_obj:
        raise HTTPException(status_code=404, detail="Facility not found")

    # ce = request.app.client_encryption
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    # ---------------- Pharmacy ----------------
    pharmacy = await Pharmacies.find(
        Pharmacies.facility_id.id == facility_obj.id,
        Pharmacies.created_by.id == user.id
    ).sort("-created_at").to_list()
    search_lower = search.lower() if search else None

  

    # ---------------- RESPONSE ----------------
    result = []
    for ph in pharmacy:
        pharmacy_name = _decrypt_value(ce, ph.pharmacy_name)
        address = _decrypt_value(ce, ph.address)
        # 🔎 Search logiic
        if search_lower:
            if (
                search_lower not in str(pharmacy_name or "").lower()
                and search_lower not in str(address or "").lower()
            ):
                continue
        result.append({
            "id": str(ph.id),
            "pharmacy_name": _decrypt_value(ce, ph.pharmacy_name),
            "phone": _decrypt_value(ce, ph.phone),
            "address": _decrypt_value(ce, ph.address),
            "fax": _decrypt_value(ce, ph.fax),
            "after_hours_phone": _decrypt_value(ce, ph.after_hours_phone),
            "contract_file_id": _decrypt_value(ce, ph.contract_file_id),
            "delivery_schedule": _decrypt_value(ce, ph.delivery_schedule),
            "created_at": ph.created_at,
            "updated_at": ph.updated_at,
        })
    
    total = len(result)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_docs = result[start:end]
    
    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Pharmacy",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Pharmacies fetched successfully",
        )
    except Exception:
        pass

    return {
        "items": paginated_docs,
        "pagination" : {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": (total + page_size - 1) // page_size,
        }
    }


@router.put("/update/pharmacy/{pharmacy_id}/")
async def update_pharmacy(
    pharmacy_id: str,
    payload: PharmaciesSchema,
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
        pharmacy_obj = None
        try:
            pharmacy_obj_id = PydanticObjectId(pharmacy_id)
            pharmacy_obj = await Pharmacies.get(pharmacy_obj_id)
        except Exception:
            pass
        if pharmacy_obj is None:
            pharmacy_obj = await Pharmacies.get(pharmacy_id)
        if not pharmacy_obj:
            raise HTTPException(status_code=404, detail="Pharmacy not found")
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")  
        def enc_or_none(val):
            return encrypt_value(ce, dek_id, val) if val is not None else None
        if payload.pharmacy_name is not None:
            pharmacy_obj.pharmacy_name = enc_or_none(payload.pharmacy_name)
        if payload.phone is not None:
            pharmacy_obj.phone = enc_or_none(payload.phone)
        if payload.address is not None:
            pharmacy_obj.address = enc_or_none(payload.address)
        if payload.fax is not None:
            pharmacy_obj.fax = enc_or_none(payload.fax)
        if payload.after_hours_phone is not None:
            pharmacy_obj.after_hours_phone = enc_or_none(payload.after_hours_phone)
        if payload.contract_file_id is not None:
            pharmacy_obj.contract_file_id = enc_or_none(payload.contract_file_id)
        if payload.delivery_schedule is not None:
            pharmacy_obj.delivery_schedule = enc_or_none(payload.delivery_schedule)
        pharmacy_obj.updated_at = datetime.now(timezone.utc)
        await pharmacy_obj.save()
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Update",
            resource="Pharmacy",
            resource_id=str(pharmacy_obj.id),
            status="success",
            notes="Pharmacy updated successfully",
        )
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating pharmacy"
        )
    