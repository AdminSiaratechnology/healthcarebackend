from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from beanie import PydanticObjectId
from pydantic import ValidationError
# from app.schemas.facility import FacilityPayload

from app.facility.models.facility import Facility
from app.facility.models.beds import Beds
from app.facility.models.facility_branding import FacilityBranding
from app.schemas.facility import FacilityCreate, BrandingInfo, StructureInfo

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value
from app.utils.audit import log_audit
import json
import os
import uuid



router = APIRouter(prefix="/facility", tags=["Facility"])



def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return json.loads(decrypted_raw)


@router.post("")
async def create_facility(
    request: Request,
    payload: FacilityCreate,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        ce = request.app.client_encryption
        dek = request.app.dek_id

        body = json.dumps({
            "basic_info": payload.basic_info.model_dump(),
            "address_info": payload.address_info.model_dump(),
        })

        enc_basic = encrypt_value(ce, dek, body)

        facility = Facility(
            basic=enc_basic,
            created_by=user,
        )
        await facility.insert()

        await log_audit(
            request=request,
            user_id=current_user_id,
            action="CREATE",
            resource="facility",
            resource_id=str(facility.id),
            status="success",
            notes=f"Facility created by {current_user_id}"
        )

        return {
            "id": str(facility.id),
            "created_at": facility.created_at,
            "updated_at": facility.updated_at,
        }
    except HTTPException:
        raise
    except ValidationError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="CREATE",
            resource="facility",
            resource_id="N/A",
            status="failed",
            notes=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))






@router.get("")
async def get_facilities_for_user(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    page: int = 1,
    page_size: int = 10,
    facility_type: str | None = None,
    facility_name: str | None = None,
    street_address: str | None = None,
):
    try:
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        facilities = await Facility.find(Facility.created_by.id == user.id).to_list()

        ce = request.app.client_encryption
        page = 1 if page < 1 else page
        page_size = 1 if page_size < 1 else (100 if page_size > 100 else page_size)

        filtered = []
        for facility in facilities:
            data = _decrypt_json_field(ce, facility.basic)
            bi = (data or {}).get("basic_info") or {}
            ai = (data or {}).get("address_info") or {}
            if facility_type and str(bi.get("facility_type", "")).lower() != facility_type.lower():
                continue
            if facility_name and facility_name.lower() not in str(bi.get("facility_name", "")).lower():
                continue
            if street_address and street_address.lower() not in str(ai.get("street_address", "")).lower():
                continue
            filtered.append((facility, bi, ai))

        total = len(filtered)
        start = (page - 1) * page_size
        end = start + page_size

        items = []
        for facility, bi, ai in filtered[start:end]:
            count_link = await Beds.find(Beds.facility_id.id == facility.id).count()
            count_str = await Beds.find(Beds.facility_id == str(facility.id)).count()
            total_beds = count_link + count_str
            items.append({
                "id": str(facility.id),
                "basic_info": bi,
                "address_info": ai,
                "total_beds": total_beds,
                "created_at": facility.created_at,
                "updated_at": facility.updated_at,
            })

        await log_audit(
            request=request,
            user_id=current_user_id,
            action="READ",
            resource="facility",
            resource_id="list",
            status="success",
            notes=f"Facilities fetched by {current_user_id}"
        )

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": ((total + page_size - 1) // page_size),
        }
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            action="READ",
            resource="facility",
            resource_id="list",
            status="failed",
            notes=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{facility_id}")
async def get_facility_by_id(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        try:
            obj_id = PydanticObjectId(facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")

        facility = await Facility.get(obj_id)
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        # Role-based access: admin/super_admin can access any facility
        ce = request.app.client_encryption
        role_val = None
        if user.role is not None:
            try:
                r = decrypt_value(ce, user.role)
                role_val = r.decode("utf-8") if isinstance(r, (bytes, bytearray)) else r
            except Exception:
                role_val = None

        is_admin = role_val in {"admin", "super_admin"}
        owner_id = getattr(facility.created_by, "id", None)
        if not is_admin and owner_id is not None and owner_id != user.id:
            raise HTTPException(status_code=403, detail="Forbidden")

        data = _decrypt_json_field(ce, facility.basic)
        bi = (data or {}).get("basic_info") or {}
        ai = (data or {}).get("address_info") or {}

       

        await log_audit(
            request=request,
            user_id=current_user_id,
            action="READ",
            resource="facility",
            resource_id=str(facility.id),
            status="success",
            notes=f"Facility fetched by {current_user_id}"
        )

        return {
            "id": str(facility.id),
            "basic_info": bi,
            "address_info": ai,
            "created_at": facility.created_at,
            "updated_at": facility.updated_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="READ",
            resource="facility",
            resource_id=facility_id,
            status="failed",
            notes=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))
