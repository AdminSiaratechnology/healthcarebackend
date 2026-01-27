from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key,encrypt_dict
from app.utils.audit import log_audit
from app.schemas.facilities.transport_vendor import TransportVendorSchema
from app.facility.models.transport_vendor import TransportVendorDocs
from bson import ObjectId
import re
from typing import Optional
from beanie.operators import Or, RegEx,And

router = APIRouter(prefix="/vendor", tags=["Transport-vendor"])


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw


# @router.post("/transport-vendor/create/{facility_id}/")
# async def create_transport_vendor(
#     facility_id: str,
#     payload: TransportVendorSchema,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce
#         dek_id = getattr(request.app, "dek_id", None)
#         if dek_id is None:
#             dek_id = ensure_data_key()
#             request.app.dek_id = dek_id

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

#         enc_vendor = encrypt_value(ce, dek_id, payload.vendor_name) if payload.vendor_name is not None else None
#         enc_contact = encrypt_value(ce, dek_id, payload.contact_number) if payload.contact_number is not None else None

#         doc = TransportVendorDocs(
#             facility_id=facility,
#             vendor_name=enc_vendor,
#             contact_number=enc_contact,
#             created_by=user,
#             created_at=datetime.now(timezone.utc),
#             updated_at=datetime.now(timezone.utc),
#         )
#         await doc.insert()

#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Create",
#             resource="Transport Vendor",
#             resource_id=str(doc.id),
#             status="success",
#             notes="Transport vendor created",
#         )

#         return {"status":"success","id": str(doc.id)}
#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=current_user_id,
#                 action="Create",
#                 resource="Transport Vendor",
#                 resource_id="N/A",
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail=str(e))


@router.post("/create/{facility_id}/")
async def create_facility_transport_vendor(
    facility_id: str,
    payload: TransportVendorSchema,
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

        # 3️⃣ Facility ownership check (soft-delete aware)
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

        # 4️⃣ Normalize for searchable fields & duplicate check
        normalized_name = payload.vendor_name.strip().lower() if payload.vendor_name else None
        normalized_contact = payload.contact_number.strip().lower() if payload.contact_number else None

        # 5️⃣ Duplicate check on contact number (same facility mein same number allowed nahi)
        if normalized_contact:
            existing = await TransportVendorDocs.find_one(
                TransportVendorDocs.facility_id.id == facility.id,
                TransportVendorDocs.vendor_contact_no_search == normalized_contact,
                TransportVendorDocs.is_deleted == False
            )
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail="Contact number already exists for another transport vendor in this facility"
                )

        # 6️⃣ Encrypt fields
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "vendor_name": payload.vendor_name,
                "contact_number": payload.contact_number,
            }
        )

        # 7️⃣ Save
        vendor_doc = TransportVendorDocs(
            facility_id=facility,
            created_by=user,
            
            vendor_name=encrypted["vendor_name"],
            contact_number=encrypted["contact_number"],
            
            vendor_name_search=normalized_name,
            vendor_contact_no_search=normalized_contact,
            
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await vendor_doc.insert()

        # 8️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Transport Vendor",
                resource_id=str(vendor_doc.id),
                status="success",
                notes=f"Transport vendor created: {payload.vendor_name or 'Unnamed'} (contact: {payload.contact_number or 'N/A'})",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "transport_vendor_id": str(vendor_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating transport vendor"
        )

# @router.get("/transport-vendor/get/{facility_id}/")
# async def get_transport_vendors(
#     facility_id: str,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
        
#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         facility_obj = None
#         try:
#             facility_obj_id = PydanticObjectId(facility_id)
#             facility_obj = await Facility.get(facility_obj_id)
#         except Exception:
#             pass
#         if facility_obj is None:
#             facility_obj = await Facility.get(facility_id)
#         if not facility_obj:
#             raise HTTPException(status_code=404, detail="Facility not found")


#         # ---------------- ENCRYPTION ----------------
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce

#         # ---------------- Transport Vendor  ----------------
#         transport_vendor = await TransportVendorDocs.find(
#             TransportVendorDocs.facility_id.id == facility_obj.id,
#             TransportVendorDocs.created_by.id == user.id
#         ).sort("-created_at").to_list()


#         # ---------------- RESPONSE ----------------
        
       

#         result = [
#             {
#                 "id": str(tv.id),
#                 "vendor_name": _decrypt_value(ce, tv.vendor_name),
#                 "contact_number": _decrypt_value(ce, tv.contact_number),
#                 "created_at": tv.created_at,
#                 "updated_at": tv.updated_at,
#             } for tv in transport_vendor
#         ]

#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Read",
#                 resource="Transport Vendor",
#                 resource_id=str(facility_obj.id),
#                 status="success",
#                 notes="Transport vendors fetched",
#             )
#         except Exception:
#             pass

#         return result
#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=current_user_id,
#                 action="Read",
#                 resource="Transport Vendor",
#                 resource_id=facility_id,
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail=str(e))


@router.get("/list/")
async def get_facility_transport_vendors(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    search: Optional[str] = Query(None, description="Search by vendor name or facility name"),
    status: Optional[str] = Query(None, description="Filter by status"),
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
        # 3️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 4️⃣ Query conditions + search handling
        # ----------------------------
        conditions = [
            TransportVendorDocs.created_by.id == user.id,
            TransportVendorDocs.is_deleted == False
        ]

        if status:
            conditions.append(TransportVendorDocs.status == status.lower())

        transport_vendors = []
        total = 0

        if search:
            search_value = search.lower()
            conditions.append(
                Or(
                    RegEx(TransportVendorDocs.vendor_contact_no_search, f"^{search_value}"),
                    RegEx(TransportVendorDocs.facility_id.facility_name_search, f"^{search_value}"),
                    RegEx(TransportVendorDocs.vendor_name_search, f"^{search_value}"),
                    
                )
               
            )

        
            
           
           

            transport_vendors = await (
                TransportVendorDocs.find(*conditions, fetch_links=True)
                .sort("-created_at")
                .skip(skip)
                .limit(page_size)
                .to_list()
            )
            total = await TransportVendorDocs.find(*conditions).count()
        else:
            # No search → normal query
            transport_vendors = await (
                TransportVendorDocs.find(*conditions, fetch_links=True)
                .sort("-created_at")
                .skip(skip)
                .limit(page_size)
                .to_list()
            )
            total = await TransportVendorDocs.find(*conditions).count()

        # ----------------------------
        # 5️⃣ Response (decrypt fields)
        # ----------------------------

        result = []
        for vendor in transport_vendors:
            result.append({
                "id": str(vendor.id),
                "facility_id": str(vendor.facility_id.id) if vendor.facility_id else None,
                "facility_name": (
                    vendor.facility_id.facility_name_search
                    if vendor.facility_id else None
                ),
                "vendor_name": decrypt_value(ce, vendor.vendor_name),
                "contact_number": decrypt_value(ce, vendor.contact_number),
                "status": vendor.status,
                "created_at": vendor.created_at,
                "updated_at": vendor.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Transport Vendors",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Transport Vendors fetched | "
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



@router.put("/update/{transport_vendor_id}/")
async def update_facility_transport_vendor(
    transport_vendor_id: str,
    payload: TransportVendorSchema,
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

        # 3️⃣ Get Transport Vendor
        try:
            vendor_obj_id = ObjectId(transport_vendor_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Transport Vendor ID")

        vendor = await TransportVendorDocs.find_one(
            TransportVendorDocs.id == vendor_obj_id,
            TransportVendorDocs.created_by.id == user.id,
            TransportVendorDocs.is_deleted == False,
            fetch_links=True
        )

        if not vendor:
            raise HTTPException(status_code=404, detail="Transport vendor not found")

        # 4️⃣ Normalize & duplicate check if vendor_name is changing
        if payload.vendor_name is not None:
            normalized_new_name = payload.vendor_name.strip().lower()

            duplicate = await TransportVendorDocs.find_one(
                TransportVendorDocs.facility_id.id == vendor.facility_id.id,
                TransportVendorDocs.vendor_name_search == normalized_new_name,
                TransportVendorDocs.id != vendor.id,
                TransportVendorDocs.is_deleted == False,
            )
            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="Another transport vendor with this name already exists in this facility"
                )

            vendor.vendor_name_search = normalized_new_name
            vendor.vendor_name = encrypt_value(ce, dek_id, payload.vendor_name)

        # 5️⃣ Update other fields (if provided)
        if payload.contact_number is not None:
            vendor.vendor_contact_no_search = payload.contact_number.strip().lower()
            vendor.contact_number = encrypt_value(ce, dek_id, payload.contact_number)

        # 6️⃣ Timestamp
        vendor.updated_at = datetime.now(timezone.utc)

        await vendor.save()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Transport Vendor",
                resource_id=str(vendor.id),
                status="success",
                notes="Transport vendor updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "transport_vendor_id": str(vendor.id),
            "message": "Transport vendor updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating transport vendor"
        )