from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.accreditations import AccreditationsSchema
from beanie import PydanticObjectId
import json
import os
from app.facility.models.accreditations import AccerditationsDoc
from bson import ObjectId
from typing import Optional
import re
from datetime import date, datetime

router = APIRouter(prefix="/accreditations", tags=["Accreditations"])


def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return json.loads(decrypted_raw)


# @router.post("/create/accreditations/{facility_id}/")
# async def create_accreditations(
#     facility_id: str,
#     acc: AccreditationsSchema,
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

#         def enc_json_or_none(val):
#             return (
#                 encrypt_value(
#                     client_encryption,
#                     dek_id,
#                     json.dumps(val)
#                 ) if val is not None else None
#             )

#         acc_body = acc.accreditations.value if acc.accreditations is not None else None
#         status_val = acc.status.value if acc.status is not None else None
#         expiry_val = acc.expiry_date.isoformat() if acc.expiry_date is not None else None
#         cert_id = acc.certificate_file_id if acc.certificate_file_id is not None else None

#         doc = AccerditationsDoc(
#             facility_id=facility,
#             accreditations=enc_json_or_none(acc_body),
#             status=enc_json_or_none(status_val),
#             expiry_date=enc_json_or_none(expiry_val),
#             certificate_file_id=enc_json_or_none(cert_id),
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
#                 resource="Accreditations",
#                 resource_id=str(doc.id),
#                 status="success",
#                 notes="Accreditations created successfully",
#             )
#         except Exception:
#             pass

#         return {
#             "success": True,
#             "facility_id_received": str(facility.id),
#             "accreditations_id": str(doc.id),
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(current_user_id),
#                 action="Create",
#                 resource="Accreditations",
#                 resource_id="N/A",
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail="Internal Server Error while creating accreditations")


@router.post("/create/{facility_id}/")
async def create_facility_accreditation(
    facility_id: str,
    payload: AccreditationsSchema,
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

        # 4️⃣ Normalize accreditation body for duplicate & search
        if not payload.accreditations_body:
            raise HTTPException(status_code=400, detail="Accreditations body is required")

        normalized_body = payload.accreditations_body.value.strip().lower()

        # 5️⃣ Duplicate validation (same body same facility mein nahi)
        existing = await AccerditationsDoc.find_one(
            AccerditationsDoc.facility_id.id == facility.id,
            AccerditationsDoc.accreditation_body_search == normalized_body,
            AccerditationsDoc.is_deleted == False
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Accreditation with this body already exists for this facility"
            )

        # 6️⃣ Custom date serializer
        def date_serializer(obj):
            if isinstance(obj, date):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        # 7️⃣ Encrypt each field
        body_enc = encrypt_value(ce, dek_id, payload.accreditations_body.value)
        status_enc = encrypt_value(ce, dek_id, payload.accreditation_status.value)
        expiry_enc = encrypt_value(ce, dek_id, payload.expiry_date.isoformat())
        cert_file_enc = encrypt_value(ce, dek_id, payload.certificate_file_id) if payload.certificate_file_id else None

        # 8️⃣ Save
        accreditation_doc = AccerditationsDoc(
            facility_id=facility,
            created_by=user,
            
            accreditations_body=body_enc,
            accreditation_status=status_enc,
            expiry_date=expiry_enc,
            certificate_file_id=cert_file_enc,
            
            accreditation_body_search=normalized_body,
            
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await accreditation_doc.insert()

        # 9️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Accreditation",
                resource_id=str(accreditation_doc.id),
                status="success",
                notes="Facility accreditation created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "accreditation_id": str(accreditation_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility accreditation"
        )


@router.get("/list/")
async def get_facility_accreditations(
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
        # 3️⃣ Query conditions
        # ----------------------------
        conditions = [
            AccerditationsDoc.created_by.id == user.id,
            AccerditationsDoc.is_deleted == False
        ]

        if status:
            conditions.append(AccerditationsDoc.status == status.lower())

        if search:
            search_value = search.lower()
            conditions.append(
                AccerditationsDoc.accreditation_body_search == re.compile(f".*{search_value}.*", re.IGNORECASE)
            )

        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------

        accreditations = await (
            AccerditationsDoc.find(
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
        total = await AccerditationsDoc.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response (decrypt fields)
        # ----------------------------

        result = []
        for acc in accreditations:
            result.append({
                "id": str(acc.id),
                "facility_id": str(acc.facility_id.id) if acc.facility_id else None,
                "facility_name": (
                    acc.facility_id.facility_name_search
                    if acc.facility_id else None
                ),
                "accreditations_body": decrypt_value(ce, acc.accreditations_body),
                "accreditation_status": decrypt_value(ce, acc.accreditation_status),
                "expiry_date": decrypt_value(ce, acc.expiry_date),
                "certificate_file_id": decrypt_value(ce, acc.certificate_file_id),
                
                "status": acc.status,
                "created_at": acc.created_at,
                "updated_at": acc.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Accreditations",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Accreditations fetched | "
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



@router.put("/update/{accreditation_id}/")
async def update_facility_accreditation(
    accreditation_id: str,
    payload: AccreditationsSchema,
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

        # 3️⃣ Get Accreditation
        try:
            acc_obj_id = ObjectId(accreditation_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Accreditation ID")

        acc = await AccerditationsDoc.find_one(
            AccerditationsDoc.id == acc_obj_id,
            AccerditationsDoc.created_by.id == user.id,
            AccerditationsDoc.is_deleted == False,
            fetch_links=True
        )

        if not acc:
            raise HTTPException(status_code=404, detail="Accreditation not found")

        # 4️⃣ Normalize & duplicate check if body changing
        if payload.accreditations_body is not None:
            normalized_new_body = payload.accreditations_body.value.strip().lower()

            duplicate = await AccerditationsDoc.find_one(
                AccerditationsDoc.facility_id.id == acc.facility_id.id,
                AccerditationsDoc.accreditation_body_search == normalized_new_body,
                AccerditationsDoc.id != acc.id,
                AccerditationsDoc.is_deleted == False,
            )
            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="Another accreditation with this body already exists"
                )

            acc.accreditation_body_search = normalized_new_body
            acc.accreditations_body = encrypt_value(ce, dek_id, payload.accreditations_body.value)

        # 5️⃣ Custom date serializer
        def date_serializer(obj):
            if isinstance(obj, date):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        # 6️⃣ Update encrypted fields (partial update)
        if payload.accreditation_status is not None:
            acc.accreditation_status = encrypt_value(ce, dek_id, payload.accreditation_status.value)

        if payload.expiry_date is not None:
            expiry_json = json.dumps({"expiry_date": payload.expiry_date}, default=date_serializer)
            acc.expiry_date = encrypt_value(ce, dek_id, payload.expiry_date.isoformat())

        if payload.certificate_file_id is not None:
            acc.certificate_file_id = encrypt_value(ce, dek_id, payload.certificate_file_id)

        # 7️⃣ Timestamp
        acc.updated_at = datetime.now(timezone.utc)

        await acc.save()

        # 8️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Accreditation",
                resource_id=str(acc.id),
                status="success",
                notes="Facility accreditation updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "accreditation_id": str(acc.id),
            "message": "Facility accreditation updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating facility accreditation"
        )