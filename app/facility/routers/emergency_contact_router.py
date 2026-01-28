from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from typing import Optional
from beanie.operators import RegEx,Or,And
from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key,encrypt_dict
from app.utils.audit import log_audit
from app.schemas.facilities.emergency_contact import emergency_contact_Schema
from beanie import PydanticObjectId

import json
import os
from app.facility.models.emergency_contact import EmergencyContactDocs


router = APIRouter(prefix="/emergency", tags=["Emergency-contact"])


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw



@router.post("/create/{facility_id}/")
async def create_emergency_contact(
    facility_id: str,
    payload: emergency_contact_Schema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # 1️⃣ User
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

        try:
            facility_obj_id = ObjectId(facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")

        
        # 3️⃣ Facility ownership check
        facility = await Facility.find_one({
            "_id": facility_obj_id,
            "created_by.$id": ObjectId(user.id),
            # "is_deleted": False
        })
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")
        

        # 6️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        existing = await EmergencyContactDocs.find_one({
            "facility_id.$id": facility.id,
            
            "is_deleted": False
        })

       





      
        normalized_role_search = payload.role.strip().lower()
        normalized_phone_search = payload.phone.strip().lower()

        existing = await EmergencyContactDocs.find_one(
                EmergencyContactDocs.facility_id.id == facility.id,
                EmergencyContactDocs.role_search == normalized_role_search,
                EmergencyContactDocs.is_deleted == False
            )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="emergency role already exists in this facility"
            )
         # 7️⃣ Random encryption (actual storage)
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "role": payload.role,
                "phone": payload.phone,
                "after_hour": payload.after_hour,
                
            }
        )

        doc = EmergencyContactDocs(
            facility_id=facility,
            role=encrypted["role"],
            phone=encrypted["phone"],
            after_hour=encrypted["after_hour"],
            role_search = normalized_role_search,
            phone_search = normalized_phone_search,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await doc.insert()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Create",
            resource="Emergency Contact",
            resource_id=str(doc.id),
            status="success",
            notes="Emergency contact created",
        )

        return {"status": "success","id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Create",
                resource="Emergency Contact",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))



# @router.get("/emergency-contact/get/{facility_id}/")
# async def get_emergency_contacts(
#     facility_id: str,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     # ---------------- USER ----------------
#     user = await UserDoc.get(current_user_id)
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     # ---------------- FACILITY ----------------
#     try:
#         facility = await Facility.get(PydanticObjectId(facility_id))
#     except Exception:
#         facility = await Facility.get(facility_id)

#     if not facility:
#         raise HTTPException(status_code=404, detail="Facility not found")

#     # ---------------- ENCRYPTION ----------------
#     ce = getattr(request.app, "client_encryption", None)
#     if ce is None:
#         ce = init_encryption()
#         request.app.client_encryption = ce

#     # ---------------- EMERGENCY CONTACTS ----------------
#     contacts = await EmergencyContactDocs.find(
#         EmergencyContactDocs.facility_id.id == facility.id,
#         EmergencyContactDocs.created_by.id == user.id
#     ).sort("-created_at").to_list()

#     # ---------------- RESPONSE ----------------
#     result = [
#         {
#             "id": str(ec.id),
#             "role": _decrypt_value(ce, ec.role),
#             "phone": _decrypt_value(ce, ec.phone),
#             "after_hour": _decrypt_value(ce, ec.after_hour),
#             "created_at": ec.created_at,
#             "updated_at": ec.updated_at,
#         } for ec in contacts
#     ]

#     # ---------------- AUDIT ----------------
#     try:
#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Read",
#             resource="Emergency Contact",
#             resource_id=str(facility.id),
#             status="success",
#             notes="Emergency contacts fetched successfully",
#         )
#     except Exception:
#         pass

#     return result



@router.get("/list/")
async def get_quality(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    search: Optional[str] = Query(None),
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
            EmergencyContactDocs.created_by.id == user.id,
            EmergencyContactDocs.is_deleted == False
        ]

        if status:
            conditions.append(EmergencyContactDocs.status == status.lower())


        
        if search:
            search_value = search.lower()
            conditions.append(
                Or(
                    RegEx(EmergencyContactDocs.role_search, f"^{search_value}"),
                    RegEx(EmergencyContactDocs.phone_search, f"^{search_value}"),
                    RegEx(EmergencyContactDocs.facility_id.facility_name_search, f"^{search_value}"),
                   
                )
               
            )

       
        
        
        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------
        emergency_cont = await (
            EmergencyContactDocs.find(
                *conditions,
                fetch_links=True
            )
            .sort("-created_at")
            .skip(skip)
            .limit(page_size)
            .to_list()
        )

        # ----------------------------
        # 6️⃣ Total count (IMPORTANT)
        # ----------------------------
        total = await EmergencyContactDocs.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------
        result = []
        for emergency in emergency_cont:
            result.append({
                "id": str(emergency.id),
                "role": decrypt_value(ce, emergency.role),
                "phone": decrypt_value(ce, emergency.phone),
                "after_hour": decrypt_value(ce, emergency.after_hour),
                "facility_id": str(emergency.facility_id.id) if emergency.facility_id else None,
                "facility_name": (
                    emergency.facility_id.facility_name_search
                    if emergency.facility_id else None
                ),
                "status": emergency.status,
                "created_at": emergency.created_at,
                "updated_at": emergency.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Facility Emergency Contact",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Emergency Contact fetched | "
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







@router.put("/update/{contact_id}/")
async def update_emergency_contact(
    contact_id: str,
    payload: emergency_contact_Schema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # 1️⃣ User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 2️⃣ Encryption
        ce = getattr(request.app, "client_encryption", None) or init_encryption()
        request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None) or ensure_data_key()
        request.app.dek_id = dek_id

        # 3️⃣ Validate ID
        try:
            quality_obj_id = ObjectId(contact_id)
            
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid  ID")

        # 4️⃣ Fetch block (Beanie-correct)
       
        emergency = await EmergencyContactDocs.find_one(
            EmergencyContactDocs.id == quality_obj_id,
            EmergencyContactDocs.created_by.id == user.id,
            EmergencyContactDocs.is_deleted == False,
        )
        

        

        if not emergency:
            raise HTTPException(status_code=404, detail="Emergency Contact not found")

       

       

        # 7️⃣ Encrypt & update
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "role": payload.role,
                "phone": payload.phone,
                "after_hour": payload.after_hour,
                
            }
        )

        emergency.role = encrypted["role"]
        emergency.phone = encrypted["phone"]
        emergency.after_hour = encrypted["after_hour"]
        
        emergency.updated_at = datetime.now(timezone.utc)

        await emergency.save()

        # Audit log
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Facility Emergency Contact",
                resource_id=str(emergency.id),
                status="success",
                notes="Emargency Contact updated successfully",
            )
        except Exception:
            pass


        return {
            "success": True,
            "emergency_contact_id": str(emergency.id),
            "updated_at": emergency.updated_at,
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Update",
                resource="Facility Emergency Contact",
                resource_id=str(contact_id),
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error")

