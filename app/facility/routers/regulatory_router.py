from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.regulatory import RegulatorySchema
from beanie import PydanticObjectId
import json
import os
from app.facility.models.regulatory import RegulatoryInfoDoc
from bson import ObjectId
from typing import Optional
import re
from datetime import date, datetime  # ← date ke liye import zaroori

router = APIRouter(prefix="/regulatory", tags=["Regulatory"])




@router.post("/create/{facility_id}/")
async def create_facility_regulatory_info(
    facility_id: str,
    payload: RegulatorySchema,
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
            # Facility.is_deleted == False,  # ← yeh wapas add kar do (safety ke liye)
        )
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found or you don't have permission")

        # 4️⃣ Check duplicate
        existing = await RegulatoryInfoDoc.find_one(
            RegulatoryInfoDoc.facility_id.id == facility.id,
            RegulatoryInfoDoc.is_deleted == False
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Regulatory information already exists for this facility"
            )

        # 5️⃣ Custom JSON encoder for date objects
        def date_serializer(obj):
            if isinstance(obj, date):
                return obj.isoformat()  # "YYYY-MM-DD"
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not JSON serializable")

        # 6️⃣ Encrypt each section separately with date handling
        state_license_enc = None
        if payload.state_license:
            state_data = payload.state_license.model_dump()
            state_json = json.dumps(state_data, default=date_serializer)
            state_license_enc = encrypt_value(ce, dek_id, state_json)

        federal_enc = None
        if payload.federal_certification:
            federal_data = payload.federal_certification.model_dump()
            federal_json = json.dumps(federal_data, default=date_serializer)
            federal_enc = encrypt_value(ce, dek_id, federal_json)

        onc_enc = None
        if payload.onc_certification:
            onc_data = payload.onc_certification.model_dump()
            onc_json = json.dumps(onc_data, default=date_serializer)
            onc_enc = encrypt_value(ce, dek_id, onc_json)

        # 7️⃣ Save
        regulatory_doc = RegulatoryInfoDoc(
            facility_id=facility,
            created_by=user,
            state_license=state_license_enc,
            federal_certification=federal_enc,
            onc_certification=onc_enc,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await regulatory_doc.insert()

        # 8️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Regulatory Info",
                resource_id=str(regulatory_doc.id),
                status="success",
                notes="Facility regulatory information created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "regulatory_info_id": str(regulatory_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility regulatory info"
        )

def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return json.loads(decrypted_raw)


# @router.get("/get/regulatory/{facility_id}/")
# async def get_regulatory_info(
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

#      # ---------------- ENCRYPTION ----------------
#     ce = getattr(request.app, "client_encryption", None)
#     if ce is None:
#         ce = init_encryption()
#         request.app.client_encryption = ce

#      # ---------------- Regulatory ----------------
#     regulatory = await RegulatoryInfoDoc.find(
#         RegulatoryInfoDoc.facility_id.id == facility_obj.id,
#         RegulatoryInfoDoc.created_by.id == user.id
#     ).sort("-created_at").to_list()


#     # ---------------- RESPONSE ----------------


    

#     result = [
#         {
#             "id": str(rg.id),
#             "state_license": _decrypt_json_field(ce, rg.state_license),
#             "federal_certification": _decrypt_json_field(ce, rg.federal_certification),
#             "onc_certification": _decrypt_json_field(ce, rg.onc_certification),
#             "created_at": rg.created_at,
#             "updated_at": rg.updated_at,
#         } for rg in regulatory
#     ]

#     try:
#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Read",
#             resource="Regulatory",
#             resource_id=str(facility_obj.id),
#             status="success",
#             notes="Regulatory info fetched successfully",
#         )
#     except Exception:
#         pass

#     return result


@router.get("/list/")
async def get_facility_regulatory_info(
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
        # 3️⃣ Query conditions
        # ----------------------------
        conditions = [
            RegulatoryInfoDoc.created_by.id == user.id,
            RegulatoryInfoDoc.is_deleted == False
        ]

        if status:
            conditions.append(RegulatoryInfoDoc.status == status.lower())

        if search:
            search_value = search.lower()
            # Search facility name via linked Facility model
            conditions.append(
                RegulatoryInfoDoc.facility_id.facility_name_search == re.compile(f".*{search_value}.*", re.IGNORECASE)
            )

        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------

        regulatory_list = await (
            RegulatoryInfoDoc.find(
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
        total = await RegulatoryInfoDoc.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response (decrypt each part)
        # ----------------------------

        result = []
        for reg in regulatory_list:
            state_license_dec = None
            if reg.state_license:
                try:
                    state_json = decrypt_value(ce, reg.state_license)
                    state_license_dec = json.loads(state_json)
                except:
                    pass

            federal_dec = None
            if reg.federal_certification:
                try:
                    fed_json = decrypt_value(ce, reg.federal_certification)
                    federal_dec = json.loads(fed_json)
                except:
                    pass

            onc_dec = None
            if reg.onc_certification:
                try:
                    onc_json = decrypt_value(ce, reg.onc_certification)
                    onc_dec = json.loads(onc_json)
                except:
                    pass

            result.append({
                "id": str(reg.id),
                "facility_id": str(reg.facility_id.id) if reg.facility_id else None,
                "facility_name": (
                    reg.facility_id.facility_name_search
                    if reg.facility_id else None
                ),
                "state_license": state_license_dec,
                "federal_certification": federal_dec,
                "onc_certification": onc_dec,
                "status": reg.status,
                "created_at": reg.created_at,
                "updated_at": reg.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Regulatory Info",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Regulatory Info fetched | "
                    f"page={page}, page_size={page_size}, "
                    f"status={status}, returned={len(result)}"
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



@router.put("/update/{regulatory_info_id}/")
async def update_facility_regulatory_info(
    regulatory_info_id: str,
    payload: RegulatorySchema,
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

        # 3️⃣ Get Regulatory Info
        try:
            reg_obj_id = ObjectId(regulatory_info_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Regulatory Info ID")

        reg = await RegulatoryInfoDoc.find_one(
            RegulatoryInfoDoc.id == reg_obj_id,
            RegulatoryInfoDoc.created_by.id == user.id,
            RegulatoryInfoDoc.is_deleted == False,
            fetch_links=True
        )

        if not reg:
            raise HTTPException(status_code=404, detail="Regulatory info not found")

        # 4️⃣ Custom serializer for date objects
        def date_serializer(obj):
            if isinstance(obj, date):
                return obj.isoformat()  # "YYYY-MM-DD"
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        # 5️⃣ Update encrypted fields (partial update with date handling)
        if payload.state_license is not None:
            state_data = payload.state_license.model_dump()
            state_json = json.dumps(state_data, default=date_serializer)
            reg.state_license = encrypt_value(ce, dek_id, state_json)

        if payload.federal_certification is not None:
            federal_data = payload.federal_certification.model_dump()
            federal_json = json.dumps(federal_data, default=date_serializer)
            reg.federal_certification = encrypt_value(ce, dek_id, federal_json)

        if payload.onc_certification is not None:
            onc_data = payload.onc_certification.model_dump()
            onc_json = json.dumps(onc_data, default=date_serializer)
            reg.onc_certification = encrypt_value(ce, dek_id, onc_json)

        # 6️⃣ Timestamp
        reg.updated_at = datetime.now(timezone.utc)

        await reg.save()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Regulatory Info",
                resource_id=str(reg.id),
                status="success",
                notes="Facility regulatory info updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "regulatory_info_id": str(reg.id),
            "message": "Facility regulatory info updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating facility regulatory info"
        )