from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value,init_encryption,ensure_data_key,encrypt_value_deterministic,encrypt_dict,decrypt_value
from app.utils.audit import log_audit
from app.schemas.facilities.interoperability import InteroperabilitySchema
from beanie import PydanticObjectId
from bson import ObjectId
import json
import os
from app.facility.models.interoperability import Interoperability
router = APIRouter(prefix="/interoperability", tags=["Interoperability"])
import re
from typing import Optional

# @router.post("/create/interoperability/{facility_id}/")
# async def create_interoperability(
#     facility_id: str,
#     interop: InteroperabilitySchema,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id)
# ):
#     try:
#         client_encryption = getattr(request.app, "client_encryption", None)
#         if client_encryption is None:
#             client_encryption = init_encryption()
#         dek_id = getattr(request.app, "dek_id", None)
#         if dek_id is None:
#             dek_id = ensure_data_key()

#         def enc_struct(obj):
#             return encrypt_value(client_encryption, dek_id, json.dumps(obj.model_dump()))

#         try:
#             facility_obj_id = PydanticObjectId(facility_id)
#         except Exception:
#             raise HTTPException(status_code=400, detail="Invalid Facility ID format")

#         facility = await Facility.get(facility_obj_id)
#         if not facility:
#             raise HTTPException(status_code=404, detail="Facility not found")

#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         interop_doc = Interoperability(
#             facility_id=facility,
#             interoperability=enc_struct(interop),
#             created_by=user,
#             created_at=datetime.now(timezone.utc),
#             updated_at=datetime.now(timezone.utc),
#         )

#         await interop_doc.insert()

#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Create",
#                 resource="Interoperability",
#                 resource_id=str(interop_doc.id),
#                 status="success",
#                 notes="Interoperability created successfully",
#             )
#         except Exception:
#             pass

#         return {
#             "success": True,
#             "facility_id_received": str(facility.id),
#             "interoperability_id": str(interop_doc.id),
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(current_user_id),
#                 action="Create",
#                 resource="Interoperability",
#                 resource_id="N/A",
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail="Internal Server Error while creating interoperability")

@router.post("/create/{facility_id}/")
async def create_facility_interoperability(
    facility_id: str,
    payload: InteroperabilitySchema,
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
        facility = await Facility.find_one(
            Facility.id == ObjectId(facility_id),
            Facility.created_by.id == user.id,
            # Facility.is_deleted == False,
        )
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found or you don't have permission")

        # 4️⃣ Check if interoperability already exists for this facility
        existing = await Interoperability.find_one(
            Interoperability.facility_id.id == facility.id,
            Interoperability.is_deleted == False
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Interoperability configuration already exists for this facility"
            )

        # 5️⃣ Convert payload to JSON string for encryption
        payload_json = json.dumps(payload.model_dump(exclude_none=True))

        # 6️⃣ Encrypt the entire config
        encrypted_config = encrypt_value(ce, dek_id, payload_json)

        # 7️⃣ Save
        interop_doc = Interoperability(
            facility_id=facility,
            created_by=user,
            
            interoperability=encrypted_config,
            
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await interop_doc.insert()

        # 8️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Interoperability",
                resource_id=str(interop_doc.id),
                status="success",
                notes="Facility interoperability configuration created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "interoperability_id": str(interop_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility interoperability"
        )


# @router.get("/get/interoperability/{facility_id}/")
# async def get_interoperabilities(
#     facility_id: str,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id)
# ):
#     user = await UserDoc.get(current_user_id)
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     facility_obj = None
#     try:
#         facility_obj_id = PydanticObjectId(facility_id)
#         facility_obj = await Facility.get(facility_obj_id)
#     except Exception:
#         pass

#     if facility_obj is None:
#         facility_obj = await Facility.get(facility_id)
#     if not facility_obj:
#         raise HTTPException(status_code=404, detail="Facility not found")

#     # ---------------- ENCRYPTION ----------------
#     ce = getattr(request.app, "client_encryption", None)
#     if ce is None:
#         ce = init_encryption()
#         request.app.client_encryption = ce
    
#      # ---------------- Interoperability ----------------
#     interopability = await Interoperability.find(
#         Interoperability.facility_id.id == facility_obj.id,
#         Interoperability.created_by.id == user.id
#     ).sort("-created_at").to_list()



#     # ---------------- RESPONSE ----------------

#     result = [
#         {
#             "id": str(ip.id),
#             "interoperability": _decrypt_json_field(ce, ip.interoperability),
#             "created_at": ip.created_at,
#             "updated_at": ip.updated_at,
#         } for ip in interopability
#     ]

#     try:
#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Read",
#             resource="Interoperability",
#             resource_id=str(facility_obj.id),
#             status="success",
#             notes="Interoperability fetched successfully",
#         )
#     except Exception:
#         pass

#     return result


@router.get("/list/")
async def get_facility_interoperability(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    search: Optional[str] = Query(None, description="Search by facility name"),
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
            Interoperability.created_by.id == user.id,
            Interoperability.is_deleted == False
        ]

        if status:
            conditions.append(Interoperability.status == status.lower())

        
        if search:
            search_value = search.lower()
            # Search facility name via linked Facility model
            conditions.append(
                Interoperability.facility_id.facility_name_search == re.compile(f".*{search_value}.*", re.IGNORECASE)
            )

        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data (fetch_links=True to get facility details)
        # ----------------------------

        interops = await (
            Interoperability.find(
                *conditions,
                fetch_links=True
            )
            .sort("-created_at")
            .skip(skip)
            .limit(page_size)
            .to_list()
        )

        # ----------------------------
        # 6️⃣ Total count
        # ----------------------------
        total = await Interoperability.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response (decrypt interoperability JSON)
        # ----------------------------

        result = []
        for interop in interops:
            decrypted_config = None
            if interop.interoperability:
                try:
                    decrypted_json = decrypt_value(ce, interop.interoperability)
                    decrypted_config = json.loads(decrypted_json)
                except:
                    decrypted_config = None

            result.append({
                "id": str(interop.id),
                "facility_id": str(interop.facility_id.id) if interop.facility_id else None,
                "facility_name": (
                    interop.facility_id.facility_name_search
                    if interop.facility_id else None
                ),
                "interoperability_config": decrypted_config,
                "status": interop.status,
                "created_at": interop.created_at,
                "updated_at": interop.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Interoperability",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Interoperability configs fetched | "
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



@router.put("/update/{interoperability_id}/")
async def update_facility_interoperability(
    interoperability_id: str,
    payload: InteroperabilitySchema,
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

        # 3️⃣ Get Interoperability
        try:
            interop_obj_id = ObjectId(interoperability_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Interoperability ID")

        interop = await Interoperability.find_one(
            Interoperability.id == interop_obj_id,
            Interoperability.created_by.id == user.id,
            Interoperability.is_deleted == False,
            fetch_links=True
        )

        if not interop:
            raise HTTPException(status_code=404, detail="Interoperability config not found")

        # 4️⃣ Convert payload to JSON string for encryption
        payload_json = json.dumps(payload.model_dump(exclude_none=True))

        # 5️⃣ Encrypt updated config
        encrypted_config = encrypt_value(ce, dek_id, payload_json)

        # 6️⃣ Update
        interop.interoperability = encrypted_config
        interop.updated_at = datetime.now(timezone.utc)

        await interop.save()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Interoperability",
                resource_id=str(interop.id),
                status="success",
                notes="Facility interoperability config updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "interoperability_id": str(interop.id),
            "message": "Facility interoperability updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating facility interoperability"
        )