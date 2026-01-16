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
from app.encryption.encryption import encrypt_value, decrypt_value,init_encryption, ensure_data_key,encrypt_value_deterministic
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
        # 3️⃣ Convert schema to JSON string & encrypt
        # ----------------------------
        payload_dict = {
            "basic_info": payload.basic_info.model_dump(),
            "address_info": payload.address_info.model_dump(),
        }

        json_body = json.dumps(payload_dict)
        enc_basic = encrypt_value(ce, dek, json_body)

        # ----------------------------
        # 4️⃣ Deterministic encrypt facility_name
        #    and check uniqueness per admin
        # ----------------------------
        enc_name_det = encrypt_value_deterministic(ce, dek, payload.basic_info.facility_name)

        existing = await Facility.find_one({
            "facility_name": enc_name_det,
            "created_by.$id": ObjectId(user.id)
        })

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Facility with the same name already exists for this user"
            )

        # ----------------------------
        # 5️⃣ Create Facility document
        # ----------------------------
        facility = Facility(
            basic=enc_basic,
            facility_name=enc_name_det,
            status=payload.facility_status.value, 
            created_by=user
        )
        await facility.insert()

        # ----------------------------
        # 6️⃣ Audit logging
        # ----------------------------
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="CREATE",
                resource="facility",
                resource_id=str(facility.id),
                status="success",
                notes=f"Facility created by {current_user_id}"
            )
        except Exception:
            pass  # audit failure should not break main logic

        # ----------------------------
        # 7️⃣ Response
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
        # audit on failure
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
        # 3️⃣ Base query (user scope)
        # ----------------------------
        base_query = {
            "created_by.$id": ObjectId(user.id)
        }

        # ----------------------------
        # 4️⃣ Build filtered query
        # ----------------------------
        query = base_query.copy()

        if status:
            query["status"] = status.lower()

        if search:
            enc_name = encrypt_value_deterministic(
                ce,
                request.app.dek_id,
                search
            )
            query["facility_name"] = enc_name

        # ----------------------------
        # 5️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        facilities = (
            await Facility.find(query)
            .sort("-created_at")
            .skip(skip)
            .limit(page_size)
            .to_list()
        )

        # ----------------------------
        # 6️⃣ Counts (NO filters)
        # ----------------------------
        total_facilities = await Facility.find(base_query).count()
        total_active = await Facility.find(
            {**base_query, "status": "active"}
        ).count()
        total_inactive = await Facility.find(
            {**base_query, "status": "inactive"}
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
            "total_facilities": total_facilities,
            "total_active": total_active,
            "total_inactive": total_inactive,
            "data": result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# from typing import List, Optional
# from fastapi import Query
# from bson import ObjectId
# import json


# @router.get("/facilities")
# async def get_facilities(
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),

#     # 🔹 pagination
#     page: int = Query(1, ge=1),
#     limit: int = Query(10, ge=1, le=100),

#     # 🔹 filters
#     search: Optional[str] = Query(None, description="Search by facility name"),
#     facility_type: Optional[str] = Query(None, description="hospital / clinic / lab"),
#     status: Optional[str] = Query(None, description="active / inactive / archived"),
# ):
#     try:
#         # ----------------------------
#         # 1️⃣ Fetch user
#         # ----------------------------
#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         # ----------------------------
#         # 2️⃣ Ensure encryption
#         # ----------------------------
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce

#         # ----------------------------
#         # 3️⃣ Build DB query
#         # ----------------------------
#         query = {
#             "created_by.$id": ObjectId(user.id)
#         }

#         # status filter (fast, indexed)
#         if status:
#             query["status"] = status

#         # deterministic search on facility_name
#         if search:
#             enc_name = encrypt_value_deterministic(
#                 ce,
#                 request.app.dek_id,
#                 search
#             )
#             query["facility_name"] = enc_name

#         skip = (page - 1) * limit

#         facilities = (
#             await Facility.find(query)
#             .sort("-created_at")
#             .skip(skip)
#             .limit(limit)
#             .to_list()
#         )

#         # ----------------------------
#         # 4️⃣ Decrypt + in-memory filter
#         # ----------------------------
#         result = []
#         for f in facilities:
#             decrypted = json.loads(decrypt_value(ce, f.basic)) if f.basic else {}

#             basic_info = decrypted.get("basic_info", {})
#             address_info = decrypted.get("address_info", {})

#             # facility_type filter (post-decrypt)
#             if facility_type and basic_info.get("facility_type") != facility_type:
#                 continue

#             result.append({
#                 "id": str(f.id),
#                 "facility_name": basic_info.get("facility_name"),
#                 "facility_type": basic_info.get("facility_type"),
#                 "status": f.status,  # 👈 ACTIVE / INACTIVE / ARCHIVED
#                 "basic_info": basic_info,
#                 "address_info": address_info,
#                 "created_at": (f.created_at),
#                 "updated_at": (f.updated_at),
#             })

#         return {
#             "page": page,
#             "page_size": limit,
#             "total": len(result),
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






@router.put("/basic-info/{facility_id}/")
async def update_facility_basic_info(
    facility_id: str,
    payload: FacilityCreate,
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

        ce = request.app.client_encryption
        dek = request.app.dek_id

        body = json.dumps({
            "basic_info": payload.basic_info.model_dump(),
            "address_info": payload.address_info.model_dump(),
        })

        enc_basic = encrypt_value(ce, dek, body)
        facility.basic = enc_basic
        # ✅ UPDATE STATUS ONLY IF SENT
        # ----------------------------
        if payload.facility_status is not None:
            facility.status = payload.facility_status.value
            print("Status updated to:", facility.status)

        facility.updated_at = datetime.now(timezone.utc)
        await facility.save()

        await log_audit(
            request=request,
            user_id=current_user_id,
            action="UPDATE",
            resource="facility",
            resource_id=str(facility.id),
            status="success",
            notes=f"Facility basic info updated by {current_user_id}"
        )

        return {
            "success": True,
            "id": str(facility.id),
            "updated_at": facility.updated_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="UPDATE",
            resource="facility",
            resource_id=facility_id,
            status="failed",
            notes=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e)) 
