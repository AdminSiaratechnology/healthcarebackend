from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.security import SecuritySchema
from beanie import PydanticObjectId
import json
import os
from app.facility.models.security import SecurityDoc
from bson import ObjectId
from datetime import datetime, timezone
from typing import Optional
import re
from beanie.operators import Or, RegEx

router = APIRouter(prefix="/security", tags=["Facility-Security"])


# @router.post("/create/security/{facility_id}/")
# async def create_security(
#     facility_id: str,
#     sec: SecuritySchema,
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

#         def enc_json_or_none(obj):
#             return (
#                 encrypt_value(
#                     client_encryption,
#                     dek_id,
#                     json.dumps(obj.model_dump(mode="json"))
#                 ) if obj is not None else None
#             )

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

#         doc = SecurityDoc(
#             facility_id=facility,
#             user_roles_access=enc_json_or_none(sec.user_roles_access),
#             authentication_sessions=enc_json_or_none(sec.authentication_sessions),
#             phi_export_controls=enc_json_or_none(sec.phi_export_settings),
#             breakglass_procedures=enc_json_or_none(sec.break_glass_audit),
#             privacy_policies=enc_json_or_none(sec.privacy_officer_info),
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
#                 resource="Security",
#                 resource_id=str(doc.id),
#                 status="success",
#                 notes="Facility security settings created successfully",
#             )
#         except Exception:
#             pass

#         return {
#             "success": True,
#             "facility_id_received": str(facility.id),
#             "security_id": str(doc.id),
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(current_user_id),
#                 action="Create",
#                 resource="Security",
#                 resource_id="N/A",
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail="Internal Server Error while creating security settings")



@router.post("/create/{facility_id}/")
async def create_facility_security(
    facility_id: str,
    payload: SecuritySchema,
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
            raise HTTPException(
                status_code=404,
                detail="Facility not found or you don't have permission"
            )

        # 4️⃣ Check if security config already exists (ONE-TO-ONE)
        existing = await SecurityDoc.find_one(
            SecurityDoc.facility_id.id == facility.id,
            SecurityDoc.is_deleted == False
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Security configuration already exists for this facility. Only one allowed per facility."
            )

        # 5️⃣ Custom serializer (future-proof for date/datetime)
       

        # 6️⃣ Encrypt each section separately
        phi_enc = None
        if payload.phi_export_settings:
            phi_json = json.dumps(payload.phi_export_settings.model_dump())
            phi_enc = encrypt_value(ce, dek_id, phi_json)

        breakglass_enc = None
        if payload.break_glass_audit:
            bg_json = json.dumps(payload.break_glass_audit.model_dump())
            breakglass_enc = encrypt_value(ce, dek_id, bg_json)

        privacy_enc = None
        if payload.privacy_officer_info:
            privacy_json = json.dumps(payload.privacy_officer_info.model_dump())
            privacy_enc = encrypt_value(ce, dek_id, privacy_json)

        # 7️⃣ Save
        security_doc = SecurityDoc(
            facility_id=facility,
            created_by=user,
            
            phi_export_controls=phi_enc,
            breakglass_procedures=breakglass_enc,
            privacy_policies=privacy_enc,
            
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await security_doc.insert()

        # 8️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Facility Security",
                resource_id=str(security_doc.id),
                status="success",
                notes="Facility security configuration created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "security_id": str(security_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility security"
        )


@router.get("/list/")
async def get_facility_security(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Search by facility name"),
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

        # 3️⃣ Pagination
        skip = (page - 1) * page_size

        # 4️⃣ Query conditions + search handling
        conditions = [
            SecurityDoc.created_by.id == user.id,
            SecurityDoc.is_deleted == False
        ]

        if status:
            conditions.append(SecurityDoc.status == status.lower())

        if search:
            search_value = search.lower()
            conditions.append(
                RegEx(SecurityDoc.facility_id.facility_name_search, f"^{search_value}"),
            )


        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size


         # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------
        security_list = await (
            SecurityDoc.find(*conditions, fetch_links=True)
            .sort("-created_at")
            .skip(skip)
            .limit(page_size)
            .to_list()
        )
     

        # ----------------------------
        # 6️⃣ Total count (IMPORTANT)
        # ----------------------------
        total = await SecurityDoc.find(*conditions).count()


        
            
           
                
            

        # 5️⃣ Response (decrypt each section)
        result = []
        for sec in security_list:
            phi_dec = None
            if sec.phi_export_controls:
                try:
                    phi_json = decrypt_value(ce, sec.phi_export_controls)
                    phi_dec = json.loads(phi_json)
                except:
                    phi_dec = None

            breakglass_dec = None
            if sec.breakglass_procedures:
                try:
                    bg_json = decrypt_value(ce, sec.breakglass_procedures)
                    breakglass_dec = json.loads(bg_json)
                except:
                    breakglass_dec = None

            privacy_dec = None
            if sec.privacy_policies:
                try:
                    privacy_json = decrypt_value(ce, sec.privacy_policies)
                    privacy_dec = json.loads(privacy_json)
                except:
                    privacy_dec = None

            result.append({
                "id": str(sec.id),
                "facility_id": str(sec.facility_id.id) if sec.facility_id else None,
                "facility_name": (
                    sec.facility_id.facility_name_search
                    if sec.facility_id else None
                ),
                "phi_export_settings": phi_dec,
                "break_glass_audit": breakglass_dec,
                "privacy_officer_info": privacy_dec,
                "status": sec.status,
                "created_at": sec.created_at,
                "updated_at": sec.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Facility Security",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Security configs fetched | "
                    f"page={page}, page_size={page_size}, "
                    f"status={status}, search={search}, returned={len(result)}"
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





@router.put("/update/{security_id}/")
async def update_facility_security(
    security_id: str,
    payload: SecuritySchema,
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

        # 3️⃣ Get Security config
        try:
            sec_obj_id = ObjectId(security_id)
        except Exception:
            raise HTTPException(status_code=400, detail ="Invalid Security ID")

        sec = await SecurityDoc.find_one(
            SecurityDoc.id == sec_obj_id,
            SecurityDoc.created_by.id == user.id,
            SecurityDoc.is_deleted == False,
            fetch_links=True
        )

        if not sec:
            raise HTTPException(status_code=404, detail="Facility security configuration not found")

        # 4️⃣ Custom serializer
       

        # 5️⃣ Partial update
        if payload.phi_export_settings is not None:
            phi_json = json.dumps(payload.phi_export_settings.model_dump())
            sec.phi_export_controls = encrypt_value(ce, dek_id, phi_json)

        if payload.break_glass_audit is not None:
            bg_json = json.dumps(payload.break_glass_audit.model_dump())
            sec.breakglass_procedures = encrypt_value(ce, dek_id, bg_json)

        if payload.privacy_officer_info is not None:
            privacy_json = json.dumps(payload.privacy_officer_info.model_dump())
            sec.privacy_policies = encrypt_value(ce, dek_id, privacy_json)

        # 6️⃣ Timestamp
        sec.updated_at = datetime.now(timezone.utc)

        await sec.save()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Facility Security",
                resource_id=str(sec.id),
                status="success",
                notes="Facility security configuration updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "security_id": str(sec.id),
            "message": "Facility security updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating facility security"
        )