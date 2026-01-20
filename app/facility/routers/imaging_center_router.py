from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Request, HTTPException, Depends,Query
from pydantic import ValidationError
from typing import Optional
from beanie.operators import RegEx
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value,init_encryption,ensure_data_key,encrypt_value_deterministic,encrypt_dict,decrypt_value
from app.utils.audit import log_audit
from app.schemas.facilities.Imaging_center import ImagingCenterSchema   
from beanie import PydanticObjectId
import re
from app.facility.models.imaging_center import ImagingCenter


router = APIRouter(prefix="/center", tags=["Imaging-Center"])


# @router.post("/create/imaging-center/{facility_id}/")
# async def create_imaging_center(
#     facility_id: str,
#     center: ImagingCenterSchema,
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

#         center_doc = ImagingCenter(
#             facility_id=facility,
#             center_name=enc_or_none(center.center_name),
#             phone=enc_or_none(center.phone),
#             fax=enc_or_none(center.fax),
#             turnaround_time=enc_or_none(center.turnaround_time),
#             transport_notes=enc_or_none(center.transport_notes),
#             created_by=user,
#             created_at=datetime.now(timezone.utc),
#             updated_at=datetime.now(timezone.utc),
#         )

#         await center_doc.insert()

#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Create",
#                 resource="Imaging Center",
#                 resource_id=str(center_doc.id),
#                 status="success",
#                 notes="Imaging center created successfully",
#             )
#         except Exception:
#             pass

#         return {
#             "success": True,
#             "facility_id_received": str(facility.id),
#             "imaging_center_id": str(center_doc.id),
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(current_user_id),
#                 action="Create",
#                 resource="Imaging Center",
#                 resource_id="N/A",
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail="Internal Server Error while creating imaging center")


@router.post("/create/{facility_id}/")
async def create_facility_imaging_center(
    facility_id: str,
    payload: ImagingCenterSchema,
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

        # 4️⃣ Normalize name (VERY IMPORTANT)
        if not payload.center_name:
            raise HTTPException(
                status_code=400,
                detail="Imaging center name is required"
            )

        normalized_center_name = payload.center_name.strip().lower()

        # 5️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        existing = await ImagingCenter.find_one(
            ImagingCenter.facility_id.id == facility.id,
            ImagingCenter.center_name_search == normalized_center_name,
            ImagingCenter.is_deleted == False
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Imaging center with this name already exists in this facility"
            )

        # 6️⃣ Encrypt fields
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "center_name": payload.center_name,
                "phone": payload.phone,
                "fax": payload.fax,
                "turnaround_time": payload.turnaround_time,
                "transport_notes": payload.transport_notes,
            }
        )

        # 7️⃣ Save
        imaging_doc = ImagingCenter(
            facility_id=facility,
            created_by=user,
            
            center_name=encrypted["center_name"],
            phone=encrypted["phone"],
            fax=encrypted["fax"],
            turnaround_time=encrypted["turnaround_time"],
            transport_notes=encrypted["transport_notes"],
            
            # Searchable field
            center_name_search=normalized_center_name,
            
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await imaging_doc.insert()

        # 8️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Imaging Center",
                resource_id=str(imaging_doc.id),
                status="success",
                notes="Facility imaging center created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "imaging_center_id": str(imaging_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility imaging center"
        )


# @router.get("/get/imaging-center/{facility_id}/")
# async def get_imaging_centers(
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

#     ce = getattr(request.app, "client_encryption", None)
#     if ce is None:
#         ce = init_encryption()
#         request.app.client_encryption = ce

#     # ---------------- Imaging Center  ----------------
#     imaging_center = await ImagingCenter.find(
#         ImagingCenter.facility_id.id == facility_obj.id,
#         ImagingCenter.created_by.id == user.id
#     ).sort("-created_at").to_list()
   
   


   

#     result = [
#         {
#             "id": str(ic.id),
#             "center_name": _decrypt_value(ce, ic.center_name),
#             "phone": _decrypt_value(ce, ic.phone),
#             "fax": _decrypt_value(ce, ic.fax),
#             "turnaround_time": _decrypt_value(ce, ic.turnaround_time),
#             "transport_notes": _decrypt_value(ce, ic.transport_notes),
#             "created_at": ic.created_at,
#             "updated_at": ic.updated_at,
#         } for ic in imaging_center
#     ]

#     try:
#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Read",
#             resource="Imaging Center",
#             resource_id=str(facility_obj.id),
#             status="success",
#             notes="Imaging centers fetched successfully",
#         )
#     except Exception:
#         pass

#     return result

@router.get("/list/")
async def get_facility_imaging_centers(
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
            ImagingCenter.created_by.id == user.id,
            ImagingCenter.is_deleted == False
        ]

        if status:
            conditions.append(ImagingCenter.status == status.lower())

        if search:
            search_value = search.lower()
            conditions.append(

                ImagingCenter.center_name_search == re.compile(f".*{search_value}.*")
                # partial match (contains) — zyada practical hai center names ke liye
                # agar sirf start match chahiye to: f"^{search_value}"
            )

        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------

        imaging_centers = await (
            ImagingCenter.find(
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
        total = await ImagingCenter.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------

        result = []
        for center in imaging_centers:
            result.append({
                "id": str(center.id),
                "center_name": decrypt_value(ce, center.center_name),
                "phone": decrypt_value(ce, center.phone),
                "fax": decrypt_value(ce, center.fax),
                "turnaround_time": decrypt_value(ce, center.turnaround_time),
                "transport_notes": decrypt_value(ce, center.transport_notes),
                
                "facility_id": str(center.facility_id.id) if center.facility_id else None,
                # Optional: agar facility name bhi chahiye aur Facility mein searchable field hai
                "facility_name": (
                    center.facility_id.facility_name_search
                    if center.facility_id else None
                ),
                
                "status": center.status,
                "created_at": center.created_at,
                "updated_at": center.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Imaging Centers",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Imaging Centers fetched | "
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


@router.put("/update/{imaging_center_id}/")
async def update_facility_imaging_center(
    imaging_center_id: str,
    payload: ImagingCenterSchema,
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

        # 3️⃣ Get Imaging Center
        try:
            center_obj_id = ObjectId(imaging_center_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Imaging Center ID")

        center = await ImagingCenter.find_one(
            ImagingCenter.id == center_obj_id,
            ImagingCenter.created_by.id == user.id,
            ImagingCenter.is_deleted == False,
            fetch_links=True
        )

        if not center:
            raise HTTPException(status_code=404, detail="Imaging center not found")

        # 4️⃣ Normalize & check duplicate center name (if name is being updated)
        if payload.center_name:
            normalized_center_name = payload.center_name.strip().lower()

            duplicate = await ImagingCenter.find_one(
                ImagingCenter.facility_id.id == center.facility_id.id,
                ImagingCenter.center_name_search == normalized_center_name,
                ImagingCenter.id != center.id,
                ImagingCenter.is_deleted == False,
            )
            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="Imaging center name already exists in this facility"
                )

            center.center_name_search = normalized_center_name
            center.center_name = encrypt_value(
                ce, dek_id, payload.center_name
            )

        # 5️⃣ Update encrypted fields (ONLY if provided)
        if payload.phone is not None:
            center.phone = encrypt_value(ce, dek_id, payload.phone)

        if payload.fax is not None:
            center.fax = encrypt_value(ce, dek_id, payload.fax)

        if payload.turnaround_time is not None:
            center.turnaround_time = encrypt_value(ce, dek_id, payload.turnaround_time)

        if payload.transport_notes is not None:
            center.transport_notes = encrypt_value(ce, dek_id, payload.transport_notes)

        # 6️⃣ Timestamp
        center.updated_at = datetime.now(timezone.utc)

        await center.save()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Imaging Center",
                resource_id=str(center.id),
                status="success",
                notes="Facility imaging center updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "imaging_center_id": str(center.id),
            "message": "Facility imaging center updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating facility imaging center"
        )


# @router.put("/update/imaging-center/{center_id}/")
# async def update_imaging_center(
#     center_id: str,
#     payload: ImagingCenterSchema,
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

#         def enc_or_none(val):
#             return encrypt_value(client_encryption, dek_id, val) if val is not None else None

#         center_doc = await ImagingCenter.get(PydanticObjectId(center_id))
#         if not center_doc:
#             raise HTTPException(status_code=404, detail="Imaging Center not found")

#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         center_doc.center_name = enc_or_none(payload.center_name)
#         center_doc.phone = enc_or_none(payload.phone)
#         center_doc.fax = enc_or_none(payload.fax)
#         center_doc.turnaround_time = enc_or_none(payload.turnaround_time)
#         center_doc.transport_notes = enc_or_none(payload.transport_notes)
#         center_doc.updated_at = datetime.now(timezone.utc)

#         await center_doc.save()

#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Update",
#                 resource="Imaging Center",
#                 resource_id=str(center_doc.id),
#                 status="success",
#                 notes="Imaging center updated successfully",
#             )
#         except Exception:
#             pass

#         return {
#             "success": True,
#             "imaging_center_id": str(center_doc.id),
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(current_user_id),
#                 action="Update",
#                 resource="Imaging Center",
#                 resource_id=center_id,
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail="Internal Server Error while updating imaging center")