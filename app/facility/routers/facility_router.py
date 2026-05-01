from datetime import datetime, timezone
from typing import Annotated, Optional

from bson import ObjectId
from fastapi import APIRouter, Query, Request, HTTPException, Depends, Form, UploadFile, File
from beanie import PydanticObjectId
from typing import List
from pydantic import ValidationError
# from app.schemas.facility import FacilityPayload

from app.facility.models.facility import Facility, FacilityStatus
from app.facility.models.beds import Beds
from app.facility.models.facility_branding import FacilityBranding
from app.schemas.facility import FacilityCreate, BrandingInfo, StructureInfo

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value,init_encryption, ensure_data_key,encrypt_value_deterministic,_decrypt_json_field
from app.utils.audit import log_audit
import json
import os
import uuid
import re



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
        # ----------------------------
        # 1️⃣ Fetch current user
        # ----------------------------
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # ----------------------------
        # 2️⃣ Ensure ClientEncryption & DEK
        # ----------------------------
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        dek = getattr(request.app, "dek_id", None)
        if dek is None:
            dek = ensure_data_key()
            request.app.dek_id = dek

        # ----------------------------
        # 3️⃣ Normalize facility name
        # ----------------------------
        facility_name = payload.facility_name.strip()
        facility_name_lower = facility_name.lower()

        # ----------------------------
        # 4️⃣ Duplicate check (per user)
        # ----------------------------
        existing = await Facility.find_one({
            "created_by.$id": ObjectId(user.id),
            "facility_name_search": {
                "$regex": f"^{facility_name_lower}$",
                "$options": "i"   # case-insensitive
            }
        })

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Facility '{facility_name}' already exists for this user"
            )

        # ----------------------------
        # 5️⃣ Encrypt payload (PHI only)
        # ----------------------------
        payload_dict = {
            "basic_info": payload.basic_info.model_dump(),
            "address_info": payload.address_info.model_dump(),
        }

        json_body = json.dumps(payload_dict)
        enc_basic = encrypt_value(ce, dek, json_body)

        # ----------------------------
        # 6️⃣ Create Facility
        # ----------------------------
        facility = Facility(
            basic=enc_basic,
            facility_name_search=facility_name_lower,   # plaintext
            status=payload.facility_status.value,
            created_by=user
        )
        await facility.insert()

        # ----------------------------
        # 7️⃣ Audit logging
        # ----------------------------
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="CREATE",
                resource="facility",
                resource_id=str(facility.id),
                status="success",
                notes=f"Facility '{facility_name}' created by {current_user_id}"
            )
        except Exception:
            pass

        # ----------------------------
        # 8️⃣ Response
        # ----------------------------
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
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="CREATE",
                resource="facility",
                resource_id="N/A",
                status="failed",
                notes=str(e)
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


    


@router.get("")
async def get_facilities(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    # 🔹 pagination
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    # 🔹 filters
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
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

        # ----------------------------
        # 3️⃣ Build filters (user scope)
        # ----------------------------
        filters = [Facility.created_by.id == user.id]

        if status:
            filters.append(Facility.status == status.lower())

        if search:
            search_pattern = re.compile(f"^{re.escape(search.strip())}", re.IGNORECASE)
            filters.append(Facility.facility_name_search == search_pattern)


        # ----------------------------
        # 5️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        facilities = (
            await Facility.find(*filters)
            .sort("-created_at")
            .skip(skip)
            .limit(page_size)
            .to_list()
        )

        # ----------------------------
        # 6️⃣ Counts (NO filters)
        # ----------------------------
        total_filtered = await Facility.find(*filters).count()
        total_facilities = await Facility.find(Facility.created_by.id == user.id).count()
        total_active = await Facility.find(
            Facility.created_by.id == user.id,
            Facility.status == "active"
        ).count()
        total_inactive = await Facility.find(
            Facility.created_by.id == user.id,
            Facility.status == "inactive"
        ).count()

        # ----------------------------
        # 7️⃣ Decrypt response
        # ----------------------------
        result = []
       
        for f in facilities:
            basic_info = json.loads(decrypt_value(ce, f.basic)) if f.basic else {}
            result.append({
                "id": str(f.id),
                "basic_info": basic_info.get("basic_info", {}),
                "address_info": basic_info.get("address_info", {}),
                "status": f.status,
                "created_at": f.created_at,
                "updated_at": f.updated_at
            })
        
        # ----------------------------
        # 8️⃣ Final response
        # ----------------------------
        return {
            "page": page,
            "page_size": page_size,
            "count": len(result),
            "total_pages": ((total_filtered + page_size - 1) // page_size),
            "total_facilities": total_facilities,
            "total_active": total_active,
            "total_inactive": total_inactive,
            "data": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# @router.get("")
# async def get_facilities(
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),

#     # 🔹 pagination
#     page: int = Query(1, ge=1),
#     page_size: int = Query(10, ge=1, le=100),

#     # 🔹 filters
#     search: Optional[str] = Query(None),
#     status: Optional[str] = Query(None),
# ):
#     try:
#         # 1️⃣ Fetch current user
#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         # 2️⃣ Encryption client
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce

#         # 3️⃣ Base query (user scope + status filter)
#         base_query = {"created_by.$id": ObjectId(user.id)}
#         if status:
#             base_query["status"] = status.lower()

#         # 4️⃣ Fetch all matching user scope (MongoDB-level filter)
#         facilities = await Facility.find(base_query).sort("-created_at").to_list()

#         # 5️⃣ Decrypt and filter (search across fields)
#         filtered = []
#         search_lower = search.lower() if search else None

#         for f in facilities:
#             basic_data = _decrypt_json_field(ce, f.basic) or {}
#             bi = basic_data.get("basic_info", {})
#             ai = basic_data.get("address_info", {})

#             # partial search across multiple fields
#             if search_lower:
#                 match = False
#                 for field_value in [
#                     bi.get("facility_name", ""),
#                     bi.get("facility_code", ""),
#                     ai.get("street_address", ""),
#                     ai.get("city", ""),
#                     ai.get("state", ""),
#                 ]:
#                     if search_lower in str(field_value).lower():
#                         match = True
#                         break
#                 if not match:
#                     continue

#             filtered.append((f, bi, ai))

#         # 6️⃣ Pagination
#         total = len(filtered)
#         start = (page - 1) * page_size
#         end = start + page_size
#         paginated = filtered[start:end]

#         # 7️⃣ Prepare response
#         result = []
#         for f, bi, ai in paginated:
#             result.append({
#                 "id": str(f.id),
#                 "basic_info": bi,
#                 "address_info": ai,
#                 "status": f.status,
#                 "created_at": f.created_at,
#                 "updated_at": f.updated_at
#             })

#         # 8️⃣ Return final response
#         return {
#             "page": page,
#             "page_size": page_size,
#             "count": len(result),
#             "total_facilities": total,
#             "total_pages": ((total + page_size - 1) // page_size),
#             "data": result,
#         }

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))



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






# @router.put("/basic-info/{facility_id}/")
# async def update_facility_basic_info(
#     facility_id: str,
#     payload: FacilityCreate,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         try:
#             obj_id = PydanticObjectId(facility_id)
#         except Exception:
#             raise HTTPException(status_code=400, detail="Invalid Facility ID format")

#         facility = await Facility.get(obj_id)
#         if not facility:
#             raise HTTPException(status_code=404, detail="Facility not found")

#         ce = request.app.client_encryption
#         dek = request.app.dek_id

#         body = json.dumps({
#             "basic_info": payload.basic_info.model_dump(),
#             "address_info": payload.address_info.model_dump(),
#         })

#         enc_basic = encrypt_value(ce, dek, body)
#         facility.basic = enc_basic
#         # ✅ UPDATE STATUS ONLY IF SENT
#         # ----------------------------
#         if payload.facility_status is not None:
#             facility.status = payload.facility_status.value
#             print("Status updated to:", facility.status)

#         facility.updated_at = datetime.now(timezone.utc)
#         await facility.save()

#         await log_audit(
#             request=request,
#             user_id=current_user_id,
#             action="UPDATE",
#             resource="facility",
#             resource_id=str(facility.id),
#             status="success",
#             notes=f"Facility basic info updated by {current_user_id}"
#         )

#         return {
#             "success": True,
#             "id": str(facility.id),
#             "updated_at": facility.updated_at,
#         }
#     except HTTPException:
#         raise
#     except Exception as e:
#         await log_audit(
#             request=request,
#             user_id=current_user_id,
#             action="UPDATE",
#             resource="facility",
#             resource_id=facility_id,
#             status="failed",
#             notes=str(e)
#         )
#         raise HTTPException(status_code=500, detail=str(e)) 



@router.put("/basic-info/{facility_id}/")
async def update_facility_basic_info(
    facility_id: str,
    payload: FacilityCreate,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # ----------------------------
        # 1️⃣ Fetch user
        # ----------------------------
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # ----------------------------
        # 2️⃣ Validate facility ID
        # ----------------------------
        try:
            obj_id = PydanticObjectId(facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")

        facility = await Facility.get(obj_id)
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        # ----------------------------
        # 3️⃣ Encryption client & DEK
        # ----------------------------
        ce = request.app.client_encryption
        dek = request.app.dek_id

        # ----------------------------
        # 4️⃣ Normalize facility name (SOURCE OF TRUTH)
        # ----------------------------
        facility_name = payload.basic_info.facility_name.strip()
        facility_name_search = facility_name.lower()

        # ----------------------------
        # 5️⃣ Duplicate check (per user)
        # ----------------------------
        existing = await Facility.find_one({
            "created_by.$id": ObjectId(user.id),
            "facility_name_search": facility_name_search,
            "_id": {"$ne": facility.id}
        })

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Facility '{facility_name}' already exists"
            )

        # ----------------------------
        # 6️⃣ Encrypt full payload
        # ----------------------------
        body = json.dumps({
            "basic_info": payload.basic_info.model_dump(),
            "address_info": payload.address_info.model_dump(),
        })

        enc_basic = encrypt_value(ce, dek, body)

        # ----------------------------
        # 7️⃣ Update fields
        # ----------------------------
        facility.basic = enc_basic
        facility.facility_name_search = facility_name_search

        if payload.facility_status is not None:
            facility.status = payload.facility_status.value

        facility.updated_at = datetime.now(timezone.utc)
        await facility.save()

        # ----------------------------
        # 8️⃣ Audit log
        # ----------------------------
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="UPDATE",
                resource="facility",
                resource_id=str(facility.id),
                status="success",
                notes=f"Facility '{facility_name}' updated by {current_user_id}"
            )
        except Exception:
            pass

        # ----------------------------
        # 9️⃣ Response
        # ----------------------------
        return {
            "success": True,
            "id": str(facility.id),
            "updated_at": facility.updated_at,
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="UPDATE",
                resource="facility",
                resource_id=facility_id,
                status="failed",
                notes=str(e)
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
    



