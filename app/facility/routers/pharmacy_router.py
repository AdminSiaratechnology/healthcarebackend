from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id

from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.pharmacies import PharmaciesSchema
from typing import Optional

import json
import os
from app.facility.models.pharmacies import Pharmacies

router = APIRouter(prefix="/pharmacy", tags=["Pharmacies"])


# @router.post("/create/pharmacy/{facility_id}/")
# async def create_pharmacy(
#     facility_id: str,
#     pharmacy: PharmaciesSchema,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id)
# ):
#     try:
#         client_encryption = request.app.client_encryption
#         dek_id = request.app.dek_id

#         def enc_or_none(val):
#             return encrypt_value(client_encryption, dek_id, val) if val is not None else None

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


#         pharmacy_doc = Pharmacies(
#             facility_id=facility,
#             pharmacy_name=enc_or_none(pharmacy.pharmacy_name),
#             phone=enc_or_none(pharmacy.phone),
#             address=enc_or_none(pharmacy.address),
#             fax=enc_or_none(pharmacy.fax),
#             after_hours_phone=enc_or_none(pharmacy.after_hours_phone),
#             contract_file_id=enc_or_none(pharmacy.contract_file_id),
#             delivery_schedule=enc_or_none(pharmacy.delivery_schedule),
#             created_by=user,
#             created_at=datetime.now(timezone.utc),
#             updated_at=datetime.now(timezone.utc),
#         )

#         await pharmacy_doc.insert()

#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Create",
#                 resource="Pharmacy",
#                 resource_id=str(pharmacy_doc.id),
#                 status="success",
#                 notes="Pharmacy created successfully",
#             )
#         except Exception:
#             pass

#         return {
#             "success": True,
#             "facility_id_received": str(facility.id),
#             "pharmacy_id": str(pharmacy_doc.id),
#         }

#     except HTTPException:
#         raise
#     except Exception:
#         raise HTTPException(
#             status_code=500,
#             detail="Internal Server Error while creating pharmacy"
#         )




@router.post("/create/{facility_id}/")
async def create_pharmacy(
    facility_id: str,
    payload: PharmaciesSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # ────────────────────────────────────────────────
        # 1. Fetch current user
        # ────────────────────────────────────────────────
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # ────────────────────────────────────────────────
        # 2. Encryption client & DEK initialization (same as room API)
        # ────────────────────────────────────────────────
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        # Helper to encrypt or return None
        def enc_or_none(value):
            return encrypt_value(ce, dek_id, value) if value is not None else None

        # ────────────────────────────────────────────────
        # 3. Validate & fetch facility + ownership check
        # ────────────────────────────────────────────────
        try:
            facility_obj_id = ObjectId(facility_id)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid Facility ID format"
            )

        facility = await Facility.find_one(
            Facility.id == facility_obj_id,
            Facility.created_by.id == user.id,   # ← important ownership check (same as room)
            # Facility.is_deleted == False
        )
        if not facility:
            raise HTTPException(
                status_code=404,
                detail="Facility not found"
            )

        # ────────────────────────────────────────────────
        # 4. Duplicate check (pharmacy name per facility)
        #    (normalized for case-insensitive search)
        # ────────────────────────────────────────────────
        if payload.pharmacy_name:
            normalized_name = payload.pharmacy_name.strip().lower()
            
            existing = await Pharmacies.find_one(
                Pharmacies.facility_id.id == facility.id,
                Pharmacies.pharmacy_name_search == normalized_name,
                Pharmacies.is_deleted == False
            )
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail="Pharmacy with this name already exists in the facility"
                )
        else:
            # agar name mandatory nahi hai schema mein to yeh optional rakh sakte ho
            # lekin mostly name required hona chahiye → consider making it required in schema
            pass

        # ────────────────────────────────────────────────
        # 5. Encrypt all fields
        # ────────────────────────────────────────────────
        encrypted_data = {
            "pharmacy_name": enc_or_none(payload.pharmacy_name),
            "phone": enc_or_none(payload.phone),
            "address": enc_or_none(payload.address),
            "fax": enc_or_none(payload.fax),
            "after_hours_phone": enc_or_none(payload.after_hours_phone),
            "contract_file_id": enc_or_none(payload.contract_file_id),
            "delivery_schedule": enc_or_none(payload.delivery_schedule),
        }

        # ────────────────────────────────────────────────
        # 6. Create document
        # ────────────────────────────────────────────────
        pharmacy_doc = Pharmacies(
            facility_id=facility,
            created_by=user,
            
            pharmacy_name=encrypted_data["pharmacy_name"],
            phone=encrypted_data["phone"],
            address=encrypted_data["address"],
            fax=encrypted_data["fax"],
            after_hours_phone=encrypted_data["after_hours_phone"],
            contract_file_id=encrypted_data["contract_file_id"],
            delivery_schedule=encrypted_data["delivery_schedule"],
            
            # Search field (normalized)
            pharmacy_name_search=normalized_name if payload.pharmacy_name else None,
            
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await pharmacy_doc.insert()

        # ────────────────────────────────────────────────
        # 7. Audit log (same as room)
        # ────────────────────────────────────────────────
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Pharmacy",
                resource_id=str(pharmacy_doc.id),
                status="success",
                notes=f"Pharmacy '{payload.pharmacy_name or 'Unnamed'}' created",
            )
        except Exception:
            pass  # non-blocking

        # ────────────────────────────────────────────────
        # 8. Success response
        # ────────────────────────────────────────────────
        return {
            "success": True,
            "message": "Pharmacy created successfully",
            "facility_id": str(facility.id),
            "pharmacy_id": str(pharmacy_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        # In production: proper logging karo (sentry/structlog etc.)
        print(f"❌ Pharmacy creation error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while creating pharmacy"
        )




@router.get("/list/")
async def get_facility_pharmacies(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    
    search: Optional[str] = Query(None, description="Search by pharmacy name (partial match)"),
    status: Optional[str] = Query(None, description="Filter by status (active/inactive etc.)"),
):
    try:
        # 1. Fetch current user
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 2. Encryption client init (same pattern as others)
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        # 3. Build query conditions
        conditions = [
            Pharmacies.created_by.id == user.id,      # Ownership: sirf usi user ke banaye hue
            Pharmacies.is_deleted == False
        ]

        if status:
            conditions.append(Pharmacies.status == status.lower())

        if search:
            search_value = search.strip().lower()
            conditions.append(
                Pharmacies.pharmacy_name_search.regexp(f".*{search_value}.*")  # partial match
                # Agar exact start match chahiye to: f"^{search_value}"
            )

        # 4. Pagination calc
        skip = (page - 1) * page_size

        # 5. Fetch paginated data with links
        pharmacies = await (
            Pharmacies.find(*conditions, fetch_links=True)
            .sort("-created_at")                    # Latest first
            .skip(skip)
            .limit(page_size)
            .to_list()
        )

        # 6. Total count for pagination metadata
        total = await Pharmacies.find(*conditions).count()

        # 7. Prepare response data (decrypt sensitive fields)
        result = []
        for pharmacy in pharmacies:
            result.append({
                "id": str(pharmacy.id),
                "pharmacy_name": decrypt_value(ce, pharmacy.pharmacy_name),
                "phone": decrypt_value(ce, pharmacy.phone),
                "address": decrypt_value(ce, pharmacy.address),
                "fax": decrypt_value(ce, pharmacy.fax),
                "after_hours_phone": decrypt_value(ce, pharmacy.after_hours_phone),
                "contract_file_id": decrypt_value(ce, pharmacy.contract_file_id),
                "delivery_schedule": decrypt_value(ce, pharmacy.delivery_schedule),
                
                "facility_id": str(pharmacy.facility_id.id) if pharmacy.facility_id else None,
                
                "facility_name": pharmacy.facility_id.facility_name_search if pharmacy.facility_id else None,
                
                "status": pharmacy.status,
                "created_at": pharmacy.created_at.isoformat() if pharmacy.created_at else None,
                "updated_at": pharmacy.updated_at.isoformat() if pharmacy.updated_at else None,
            })

        # 8. Audit log (non-blocking)
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Pharmacies",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Pharmacies list fetched | "
                    f"page={page}, page_size={page_size}, "
                    f"search={search or 'None'}, status={status or 'None'}, "
                    f"returned={len(result)}"
                ),
            )
        except Exception:
            pass  # fail silently

        # 9. Final response
        return {
            "success": True,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
            "count": len(result),
            "total": total,
            "data": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Pharmacy list error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while fetching pharmacies"
        )

# @router.get("/get/pharmacy/{facility_id}/")
# async def get_pharmacies(
#     facility_id: str,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
#     page: int = Query(1, ge=1),
#     page_size: int = Query(10, ge=1),
#     search: str | None = Query(None, description="Search by pharmacy name or address"),
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

#     # ce = request.app.client_encryption
#     ce = getattr(request.app, "client_encryption", None)
#     if ce is None:
#         ce = init_encryption()
#         request.app.client_encryption = ce

#     # ---------------- Pharmacy ----------------
#     pharmacy = await Pharmacies.find(
#         Pharmacies.facility_id.id == facility_obj.id,
#         Pharmacies.created_by.id == user.id
#     ).sort("-created_at").to_list()
#     search_lower = search.lower() if search else None

  

#     # ---------------- RESPONSE ----------------
#     result = []
#     for ph in pharmacy:
#         pharmacy_name = _decrypt_value(ce, ph.pharmacy_name)
#         address = _decrypt_value(ce, ph.address)
#         # 🔎 Search logiic
#         if search_lower:
#             if (
#                 search_lower not in str(pharmacy_name or "").lower()
#                 and search_lower not in str(address or "").lower()
#             ):
#                 continue
#         result.append({
#             "id": str(ph.id),
#             "pharmacy_name": _decrypt_value(ce, ph.pharmacy_name),
#             "phone": _decrypt_value(ce, ph.phone),
#             "address": _decrypt_value(ce, ph.address),
#             "fax": _decrypt_value(ce, ph.fax),
#             "after_hours_phone": _decrypt_value(ce, ph.after_hours_phone),
#             "contract_file_id": _decrypt_value(ce, ph.contract_file_id),
#             "delivery_schedule": _decrypt_value(ce, ph.delivery_schedule),
#             "created_at": ph.created_at,
#             "updated_at": ph.updated_at,
#         })
    
#     total = len(result)
#     start = (page - 1) * page_size
#     end = start + page_size
#     paginated_docs = result[start:end]
    
#     try:
#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Read",
#             resource="Pharmacy",
#             resource_id=str(facility_obj.id),
#             status="success",
#             notes="Pharmacies fetched successfully",
#         )
#     except Exception:
#         pass

#     return {
#         "items": paginated_docs,
#         "pagination" : {
#             "page": page,
#             "page_size": page_size,
#             "total_items": total,
#             "total_pages": (total + page_size - 1) // page_size,
#         }
#     }




# @router.put("/update/{pharmacy_id}/")
# async def update_pharmacy(
#     pharmacy_id: str,
#     payload: PharmaciesSchema,  # all fields optional — sirf jo change karna hai woh bhej sakte ho
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         # 1. Fetch current user
#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         # 2. Encryption init (same pattern)
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce

#         dek_id = getattr(request.app, "dek_id", None)
#         if dek_id is None:
#             dek_id = ensure_data_key()
#             request.app.dek_id = dek_id

#         def enc_or_none(value):
#             return encrypt_value(ce, dek_id, value) if value is not None else None

#         # 3. Validate pharmacy ID & fetch existing
#         try:
#             pharmacy_obj_id = ObjectId(pharmacy_id)
#         except Exception:
#             raise HTTPException(status_code=400, detail="Invalid Pharmacy ID format")

#         pharmacy = await Pharmacies.find_one(
#             Pharmacies.id == pharmacy_obj_id,
#             Pharmacies.created_by.id == user.id,     # Ownership check — sirf creator hi update kar sake
#             Pharmacies.is_deleted == False
#         )
#         if not pharmacy:
#             raise HTTPException(
#                 status_code=404,
#                 detail="Pharmacy not found or you don't have permission to update it"
#             )

#         # 4. If pharmacy_name is being updated → check for duplicate in same facility
#         new_name = payload.pharmacy_name
#         if new_name is not None:
#             normalized_new_name = new_name.strip().lower()
            
#             # Check if another pharmacy with same name exists (exclude current one)
#             duplicate = await Pharmacies.find_one(
#                 Pharmacies.facility_id.id == pharmacy.facility_id.id,
#                 Pharmacies.pharmacy_name_search == normalized_new_name,
#                 Pharmacies.id != pharmacy.id,                # ← important: current ko ignore
#                 Pharmacies.is_deleted == False
#             )
#             if duplicate:
#                 raise HTTPException(
#                     status_code=400,
#                     detail="Another pharmacy with this name already exists in the facility"
#                 )
#         else:
#             normalized_new_name = pharmacy.pharmacy_name_search  # no change

#         # 5. Prepare updates (only provided fields ko update karo)
#         update_data = {}
        
#         if payload.pharmacy_name is not None:
#             update_data["pharmacy_name"] = enc_or_none(payload.pharmacy_name)
#             update_data["pharmacy_name_search"] = normalized_new_name
        
#         if payload.phone is not None:
#             update_data["phone"] = enc_or_none(payload.phone)
#         if payload.address is not None:
#             update_data["address"] = enc_or_none(payload.address)
#         if payload.fax is not None:
#             update_data["fax"] = enc_or_none(payload.fax)
#         if payload.after_hours_phone is not None:
#             update_data["after_hours_phone"] = enc_or_none(payload.after_hours_phone)
#         if payload.contract_file_id is not None:
#             update_data["contract_file_id"] = enc_or_none(payload.contract_file_id)
#         if payload.delivery_schedule is not None:
#             update_data["delivery_schedule"] = enc_or_none(payload.delivery_schedule)

#         # Always update timestamp
#         update_data["updated_at"] = datetime.now(timezone.utc)

#         # If nothing to update → optional: return early or raise warning
#         if not update_data:
#             return {
#                 "success": True,
#                 "message": "No fields provided to update",
#                 "pharmacy_id": str(pharmacy.id)
#             }

#         # 6. Apply update
#         await pharmacy.set(update_data)

#         # 7. Audit log
#         updated_fields = ", ".join(update_data.keys())
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Update",
#                 resource="Pharmacy",
#                 resource_id=str(pharmacy.id),
#                 status="success",
#                 notes=f"Pharmacy updated | fields: {updated_fields}"
#             )
#         except Exception:
#             pass

#         # 8. Success response (current state return kar sakte ho ya simple message)
#         return {
#             "success": True,
#             "message": "Pharmacy updated successfully",
#             "pharmacy_id": str(pharmacy.id),
#             "updated_fields": list(update_data.keys()),
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         print(f"❌ Pharmacy update error: {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Internal server error while updating pharmacy"
#         )


@router.put("/update/{pharmacy_id}/")
async def update_pharmacy(
    pharmacy_id: str,
    payload: PharmaciesSchema,  # all fields Optional jaise create mein
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

        # 3️⃣ Get Pharmacy
        try:
            pharmacy_obj_id = ObjectId(pharmacy_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Pharmacy ID")

        pharmacy = await Pharmacies.find_one(
            Pharmacies.id == pharmacy_obj_id,
            Pharmacies.created_by.id == user.id,
            Pharmacies.is_deleted == False,
            fetch_links=True  # agar future mein facility details chahiye to
        )

        if not pharmacy:
            raise HTTPException(status_code=404, detail="Pharmacy not found")

        # 4️⃣ Normalize & check duplicate pharmacy name (if name is being updated)
        if payload.pharmacy_name:
            normalized_name = payload.pharmacy_name.strip().lower()

            duplicate = await Pharmacies.find_one(
                Pharmacies.facility_id.id == pharmacy.facility_id.id,
                Pharmacies.pharmacy_name_search == normalized_name,
                Pharmacies.id != pharmacy.id,
                Pharmacies.is_deleted == False,
            )
            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="Pharmacy name already exists in this facility"
                )

            pharmacy.pharmacy_name_search = normalized_name
            pharmacy.pharmacy_name = encrypt_value(
                ce, dek_id, payload.pharmacy_name
            )

        # 5️⃣ Update encrypted fields (ONLY if provided)
        if payload.phone is not None:
            pharmacy.phone = encrypt_value(ce, dek_id, payload.phone)

        if payload.address is not None:
            pharmacy.address = encrypt_value(ce, dek_id, payload.address)

        if payload.fax is not None:
            pharmacy.fax = encrypt_value(ce, dek_id, payload.fax)

        if payload.after_hours_phone is not None:
            pharmacy.after_hours_phone = encrypt_value(ce, dek_id, payload.after_hours_phone)

        if payload.contract_file_id is not None:
            pharmacy.contract_file_id = encrypt_value(ce, dek_id, payload.contract_file_id)

        if payload.delivery_schedule is not None:
            pharmacy.delivery_schedule = encrypt_value(ce, dek_id, payload.delivery_schedule)

        # 6️⃣ Timestamp
        pharmacy.updated_at = datetime.now(timezone.utc)

        await pharmacy.save()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Pharmacy",
                resource_id=str(pharmacy.id),
                status="success",
                notes="Pharmacy updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "pharmacy_id": str(pharmacy.id),
            "message": "Pharmacy updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating pharmacy"
        )