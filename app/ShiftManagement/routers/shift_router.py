
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from app.accounts.models.user import UserDoc
from app.facility.models.facility import Facility
from app.ShiftManagement.models.shift import ShiftManagementDocs
from app.schemas.ShiftManagement.shift import ShiftManagementSchema
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_dict, encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from beanie import PydanticObjectId
from beanie.operators import RegEx, Or, And
from typing import Optional, List
from bson import ObjectId

router = APIRouter(prefix="/shift_management", tags=["Shift Management"])

@router.post("/create/shift/")
async def create_shift(
    payload: ShiftManagementSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
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

        # 3️⃣ Facility validation (if facility_ids provided)
        facility_links = []
        if payload.facility_ids:
            for fid in payload.facility_ids:
                try:
                    # Using find_one to ensure facility exists and handle PydanticObjectId conversion
                    facility = await Facility.get(PydanticObjectId(fid))
                    if not facility:
                         raise HTTPException(status_code=404, detail=f"Facility with ID {fid} not found")
                    facility_links.append(facility)
                except Exception:
                     raise HTTPException(status_code=400, detail=f"Invalid Facility ID format: {fid}")

        # 4️⃣ Normalize name (VERY IMPORTANT)
        normalized_name = payload.name.strip().lower()

        # 6️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        # Check if a shift with the same name exists in any of the provided facilities?
        # Or just global uniqueness check for this user/tenant? 
        # For now, let's assume uniqueness per name for the created_by user context or similar logic if needed.
        # But looking at campusblock, it checks within facility. Shift has multiple facilities.
        # We will check if a shift with same name exists created by this user or just rely on name_search.
        
        # Checking for duplicate name within active shifts
        existing = await ShiftManagementDocs.find_one({
            "name_search": normalized_name,
            "is_deleted": False,
            # "created_by.$id": user.id # Optional: scope to user? usually resources are shared.
            # Let's keep it simple: unique name per system or facility group?
            # campusblock logic: facility_id + name. Here we have multiple facilities.
            # Let's check if any shift has same name.
        })

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Shift with this name already exists"
            )

        # 7️⃣ Random encryption (actual storage)
        encrypted_data = encrypt_dict(
            ce, 
            dek_id, 
            {
                "shift": payload.shift,
                "start_time": payload.start_time,
                "end_time": payload.end_time,
                "shift_type": payload.shift_type,
                "break_duration": payload.break_duration,
                "minumum_staff_required": payload.minumum_staff_required,
                "maximum_staff_allowed": payload.maximum_staff_allowed,
                "priority": payload.priority,
                "required_role": payload.required_role,
                "active_days": payload.active_days,
                "description": payload.description,
                "name": payload.name,
            }
        )

        # 8️⃣ Save
        shift_doc = ShiftManagementDocs(
            name_search=normalized_name,
            name=encrypted_data["name"],
            shift=encrypted_data["shift"],
            start_time=encrypted_data["start_time"],
            end_time=encrypted_data["end_time"],
            shift_type=encrypted_data["shift_type"],
            break_duration=encrypted_data["break_duration"],
            minumum_staff_required=encrypted_data["minumum_staff_required"],
            maximum_staff_allowed=encrypted_data["maximum_staff_allowed"],
            priority=encrypted_data["priority"],
            required_role=encrypted_data["required_role"],
            active_days=encrypted_data["active_days"],
            description=encrypted_data["description"],
            facility_ids=facility_links,
            created_by=user,
            status="active",
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await shift_doc.insert()

        # 9️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="CREATE",
                resource="shift_management",
                resource_id=str(shift_doc.id),
                status="success",
                notes=f"Shift {payload.name} created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "shift_id": str(shift_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/list/")
async def get_all_shifts(
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
            ShiftManagementDocs.created_by.id == user.id,
            ShiftManagementDocs.is_deleted == False
        ]

        if status:
            conditions.append(ShiftManagementDocs.status == status.lower())

        if search:
            conditions.append(
                RegEx(ShiftManagementDocs.name_search, f"^{search.lower()}")
            )

        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------
        shifts = await (
            ShiftManagementDocs.find(
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
        total = await ShiftManagementDocs.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------
        result = []
        for shift in shifts:
            result.append({
                "id": str(shift.id),
                "name": decrypt_value(ce, shift.name),
                "shift": decrypt_value(ce, shift.shift),
                "start_time": decrypt_value(ce, shift.start_time),
                "end_time": decrypt_value(ce, shift.end_time),
                "shift_type": decrypt_value(ce, shift.shift_type),
                "break_duration": decrypt_value(ce, shift.break_duration),
                "minumum_staff_required": decrypt_value(ce, shift.minumum_staff_required),
                "maximum_staff_allowed": decrypt_value(ce, shift.maximum_staff_allowed),
                "priority": decrypt_value(ce, shift.priority),
                "required_role": decrypt_value(ce, shift.required_role),
                "active_days": decrypt_value(ce, shift.active_days),
                "description": decrypt_value(ce, shift.description),
                "facility_ids": [str(f.id) for f in shift.facility_ids] if shift.facility_ids else [],
                # "facility_names": [f.facility_name_search for f in shift.facility_ids] if shift.facility_ids else [], # Assuming facility has this
                "status": shift.status,
                "created_at": shift.created_at,
                "updated_at": shift.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Shift Management",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Shifts fetched | "
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


@router.put("/update/shift/{shift_id}/")
async def update_shift(
    shift_id: str,
    payload: ShiftManagementSchema,
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
            shift_obj_id = PydanticObjectId(shift_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Shift ID")

        # 4️⃣ Fetch shift (Beanie-correct)
        shift_doc = await ShiftManagementDocs.find_one(
            ShiftManagementDocs.id == shift_obj_id,
            ShiftManagementDocs.created_by.id == user.id,
            ShiftManagementDocs.is_deleted == False,
        )

        if not shift_doc:
            raise HTTPException(status_code=404, detail="Shift not found")

        # 5️⃣ Normalize name
        normalized_name = payload.name.strip().lower()

        # 6️⃣ Duplicate validation
        if normalized_name != shift_doc.name_search:
            duplicate = await ShiftManagementDocs.find_one(
                And(
                    ShiftManagementDocs.name_search == normalized_name,
                    ShiftManagementDocs.is_deleted == False,
                    ShiftManagementDocs.id != shift_doc.id,
                )
            )

            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="Shift with this name already exists",
                )
        
        # 7️⃣ Validate Facilities
        facility_links = []
        if payload.facility_ids:
             for fid in payload.facility_ids:
                try:
                    facility = await Facility.get(PydanticObjectId(fid))
                    if not facility:
                         raise HTTPException(status_code=404, detail=f"Facility with ID {fid} not found")
                    facility_links.append(facility)
                except Exception:
                     raise HTTPException(status_code=400, detail=f"Invalid Facility ID format: {fid}")

        # 8️⃣ Encrypt & update
        encrypted_data = encrypt_dict(
            ce, 
            dek_id, 
            {
                "shift": payload.shift,
                "start_time": payload.start_time,
                "end_time": payload.end_time,
                "shift_type": payload.shift_type,
                "break_duration": payload.break_duration,
                "minumum_staff_required": payload.minumum_staff_required,
                "maximum_staff_allowed": payload.maximum_staff_allowed,
                "priority": payload.priority,
                "required_role": payload.required_role,
                "active_days": payload.active_days,
                "description": payload.description,
                "name": payload.name,
            }
        )
        
        shift_doc.name = encrypted_data["name"]
        shift_doc.name_search = normalized_name
        shift_doc.shift = encrypted_data["shift"]
        shift_doc.start_time = encrypted_data["start_time"]
        shift_doc.end_time = encrypted_data["end_time"]
        shift_doc.shift_type = encrypted_data["shift_type"]
        shift_doc.break_duration = encrypted_data["break_duration"]
        shift_doc.minumum_staff_required = encrypted_data["minumum_staff_required"]
        shift_doc.maximum_staff_allowed = encrypted_data["maximum_staff_allowed"]
        shift_doc.priority = encrypted_data["priority"]
        shift_doc.required_role = encrypted_data["required_role"]
        shift_doc.active_days = encrypted_data["active_days"]
        shift_doc.description = encrypted_data["description"]
        shift_doc.facility_ids = facility_links
        
        shift_doc.updated_at = datetime.now(timezone.utc)

        await shift_doc.save()

        # Audit log
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Shift Management",
                resource_id=str(shift_doc.id),
                status="success",
                notes="Shift updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "shift_id": str(shift_doc.id),
            "updated_at": shift_doc.updated_at,
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
                resource="Shift Management",
                resource_id=str(shift_id),
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error")
