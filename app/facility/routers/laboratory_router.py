from datetime import datetime, timezone
from beanie import PydanticObjectId
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from typing import Optional
from beanie.operators import RegEx,And,Or
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value,init_encryption,ensure_data_key,encrypt_value_deterministic,encrypt_dict,decrypt_value
from app.utils.audit import log_audit
from app.schemas.facilities.laboratory import LaboratorySchema
from beanie import PydanticObjectId
from app.facility.models.laboratory import Laboratory
from bson import ObjectId
router = APIRouter(prefix="/laboratory", tags=["Laboratories"])


# @router.post("/create/laboratory/{facility_id}/")
# async def create_laboratory(
#     facility_id: str,
#     lab: LaboratorySchema,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id)
# ):
#     try:
#         client_encryption = request.app.client_encryption
#         dek_id = request.app.dek_id

#         def enc_or_none(val):
#             if val is None:
#                 return None
#             if hasattr(val, "value"):
#                 val = val.value
#             return encrypt_value(client_encryption, dek_id, val)

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

#         lab_doc = Laboratory(
#             facility_id=facility,
#             laboratory_name=enc_or_none(lab.laboratory_name),
#             phone=enc_or_none(lab.phone),
#             fax=enc_or_none(lab.fax),
#             pickup_schedule=enc_or_none(lab.pickup_schedule),
#             interface_type=enc_or_none(lab.interface_type),
#             loinc_policy=enc_or_none(lab.loinc_policy),
#             created_by=user,
#             created_at=datetime.now(timezone.utc),
#             updated_at=datetime.now(timezone.utc),
#         )

#         await lab_doc.insert()

#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Create",
#                 resource="Laboratory",
#                 resource_id=str(lab_doc.id),
#                 status="success",
#                 notes="Laboratory created successfully",
#             )
#         except Exception:
#             pass

#         return {
#             "success": True,
#             "facility_id_received": str(facility.id),
#             "laboratory_id": str(lab_doc.id),
#         }

#     except HTTPException:
#         raise
#     except Exception:
#         raise HTTPException(
#             status_code=500,
#             detail="Internal Server Error while creating laboratory"
#         )


@router.post("/create/{facility_id}/")
async def create_facility_laboratory(
    facility_id: str,
    payload: LaboratorySchema,
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

        try:
            facility_obj_id = PydanticObjectId(facility_id)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid Facility ID format"
            )
        # 3️⃣ Facility ownership check
        facility = await Facility.find_one(
            Facility.id == facility_obj_id,
            Facility.created_by.id == user.id,
            # Facility.is_deleted == False,  # soft-delete aware
        )
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found or you don't have permission")

        # 4️⃣ Normalize name (VERY IMPORTANT for duplicate check)
        if not payload.laboratory_name:
            raise HTTPException(
                status_code=400,
                detail="Laboratory name is required"
            )

        normalized_lab_name = payload.laboratory_name.strip().lower()

        # 5️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        existing = await Laboratory.find_one(
            Laboratory.facility_id.id == facility.id,
            Laboratory.laboratory_search == normalized_lab_name,
            Laboratory.is_deleted == False
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Laboratory with this name already exists in this facility"
            )

        # 6️⃣ Encrypt all fields
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "laboratory_name": payload.laboratory_name,
                "phone": payload.phone,
                "fax": payload.fax,
                "pickup_schedule": payload.pickup_schedule,
                "interface_type": payload.interface_type.value if payload.interface_type else None,
                "loinc_policy": payload.loinc_policy.value if payload.loinc_policy else None,
            }
        )

        # 7️⃣ Save
        lab_doc = Laboratory(
            facility_id=facility,
            created_by=user,
            
            laboratory_name=encrypted["laboratory_name"],
            phone=encrypted["phone"],
            fax=encrypted["fax"],
            pickup_schedule=encrypted["pickup_schedule"],
            interface_type=encrypted["interface_type"],
            loinc_policy=encrypted["loinc_policy"],
            
            # Searchable field
            laboratory_search=normalized_lab_name,
            
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await lab_doc.insert()

        # 8️⃣ Audit log
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Laboratory",
                resource_id=str(lab_doc.id),
                status="success",
                notes="Facility laboratory created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "laboratory_id": str(lab_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility laboratory"
        )



@router.get("/list/")
async def get_facility_laboratories(
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
            Laboratory.created_by.id == user.id,
            Laboratory.is_deleted == False
        ]

        if status:
            conditions.append(Laboratory.status == status.lower())

        if search:
            search_value = search.lower()
            conditions.append(
                RegEx(Laboratory.laboratory_search, f"^{search_value}"),
                
                # partial match (contains) — zyada user-friendly
                # agar sirf start match chahiye to: f"^{search_value}"
            )

        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------

        laboratories = await (
            Laboratory.find(
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
        total = await Laboratory.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response (decrypt sensitive fields)
        # ----------------------------

        result = []
        for lab in laboratories:
            result.append({
                "id": str(lab.id),
                "laboratory_name": decrypt_value(ce, lab.laboratory_name),
                "phone": decrypt_value(ce, lab.phone),
                "fax": decrypt_value(ce, lab.fax),
                "pickup_schedule": decrypt_value(ce, lab.pickup_schedule),
                "interface_type": decrypt_value(ce, lab.interface_type),
                "loinc_policy": decrypt_value(ce, lab.loinc_policy),
                
                "facility_id": str(lab.facility_id.id) if lab.facility_id else None,
                
                "facility_name": (
                    lab.facility_id.facility_name_search
                    if lab.facility_id else None
                ),
                
                "status": lab.status,
                "created_at": lab.created_at,
                "updated_at": lab.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Laboratories",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Laboratories fetched | "
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



@router.put("/update/{laboratory_id}/")
async def update_facility_laboratory(
    laboratory_id: str,
    payload: LaboratorySchema,
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

        # 3️⃣ Get Laboratory
        try:
            lab_obj_id = ObjectId(laboratory_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Laboratory ID")

        lab = await Laboratory.find_one(
            Laboratory.id == lab_obj_id,
            Laboratory.created_by.id == user.id,
            Laboratory.is_deleted == False,
            fetch_links=True
        )

        if not lab:
            raise HTTPException(status_code=404, detail="Laboratory not found")

        # 4️⃣ Normalize & check duplicate laboratory name (if name is being updated)
        if payload.laboratory_name:
            normalized_lab_name = payload.laboratory_name.strip().lower()

            duplicate = await Laboratory.find_one(
                Laboratory.facility_id.id == lab.facility_id.id,
                Laboratory.laboratory_search == normalized_lab_name,
                Laboratory.id != lab.id,
                Laboratory.is_deleted == False,
            )
            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="Laboratory name already exists in this facility"
                )

            lab.laboratory_search = normalized_lab_name
            lab.laboratory_name = encrypt_value(
                ce, dek_id, payload.laboratory_name
            )

        # 5️⃣ Update encrypted fields (ONLY if provided)
        if payload.phone is not None:
            lab.phone = encrypt_value(ce, dek_id, payload.phone)

        if payload.fax is not None:
            lab.fax = encrypt_value(ce, dek_id, payload.fax)

        if payload.pickup_schedule is not None:
            lab.pickup_schedule = encrypt_value(ce, dek_id, payload.pickup_schedule)

        if payload.interface_type is not None:
            lab.interface_type = encrypt_value(
                ce, dek_id, payload.interface_type.value
            )

        if payload.loinc_policy is not None:
            lab.loinc_policy = encrypt_value(
                ce, dek_id, payload.loinc_policy.value
            )

        # 6️⃣ Timestamp
        lab.updated_at = datetime.now(timezone.utc)

        await lab.save()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Laboratory",
                resource_id=str(lab.id),
                status="success",
                notes="Facility laboratory updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "laboratory_id": str(lab.id),
            "message": "Facility laboratory updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating facility laboratory"
        )
# @router.get("/get/laboratory/{facility_id}/")
# async def get_laboratories(
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

#     # ---------------- Laboratory  ----------------
#     laboratory = await Laboratory.find(
#         Laboratory.facility_id.id == facility_obj.id,
#         Laboratory.created_by.id == user.id
#     ).sort("-created_at").to_list()
   
   

#     result = [
#         {
#             "id": str(lb.id),
#             "laboratory_name": _decrypt_value(ce, lb.laboratory_name),
#             "phone": _decrypt_value(ce, lb.phone),
#             "fax": _decrypt_value(ce, lb.fax),
#             "pickup_schedule": _decrypt_value(ce, lb.pickup_schedule),
#             "interface_type": _decrypt_value(ce, lb.interface_type),
#             "loinc_policy": _decrypt_value(ce, lb.loinc_policy),
#             "created_at": lb.created_at,
#             "updated_at": lb.updated_at,
#         } for lb in laboratory
#     ]

#     try:
#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Read",
#             resource="Laboratory",
#             resource_id=str(facility_obj.id),
#             status="success",
#             notes="Laboratories fetched successfully",
#         )
#     except Exception:
#         pass

#     return result


# @router.put("/update/laboratory/{laboratory_id}/")
# async def update_laboratory(
#     laboratory_id: str,
#     lab: LaboratorySchema,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id)
# ):
#     try:
#         client_encryption = request.app.client_encryption
#         dek_id = request.app.dek_id

#         def enc_or_none(val):
#             if val is None:
#                 return None
#             if hasattr(val, "value"):
#                 val = val.value
#             return encrypt_value(client_encryption, dek_id, val)

#         laboratory = await Laboratory.get(PydanticObjectId(laboratory_id))
#         if not laboratory:
#             raise HTTPException(status_code=404, detail="Laboratory not found")

#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         laboratory.laboratory_name = enc_or_none(lab.laboratory_name)
#         laboratory.phone = enc_or_none(lab.phone)
#         laboratory.fax = enc_or_none(lab.fax)
#         laboratory.pickup_schedule = enc_or_none(lab.pickup_schedule)
#         laboratory.interface_type = enc_or_none(lab.interface_type)
#         laboratory.loinc_policy = enc_or_none(lab.loinc_policy)
#         laboratory.updated_at = datetime.now(timezone.utc)

#         await laboratory.save()

#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Update",
#                 resource="Laboratory",
#                 resource_id=str(laboratory.id),
#                 status="success",
#                 notes="Laboratory updated successfully",
#             )
#         except Exception:
#             pass

#         return {
#             "success": True,
#             "laboratory_id": str(laboratory.id),
#         }

#     except HTTPException:
#         raise
#     except Exception:
#         raise HTTPException(
#             status_code=500,
#             detail="Internal Server Error while updating laboratory"
#         )   
