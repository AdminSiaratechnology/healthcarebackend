from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends,Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.facility.models.facility_department import FacilityDepartment

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import (
    encrypt_value,
    decrypt_value,
    init_encryption,
    ensure_data_key,
    encrypt_value_deterministic,
    encrypt_dict
)
from app.utils.audit import log_audit
from app.schemas.facilities.department import DepartmentSchema
from beanie import PydanticObjectId
from bson import ObjectId
from typing import Optional
from beanie.operators import Or, RegEx
import json
import os


router = APIRouter(prefix="/department", tags=["Masters"])


@router.post("/create/{facility_id}/")
async def create_facility_department(
    facility_id: str,
    payload: DepartmentSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        # 1️⃣ Validate User
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
        facility = await Facility.find_one({
            "_id": ObjectId(facility_id),
            "created_by.$id": ObjectId(user.id),
            # "is_deleted": False
        })
        
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        # 4️⃣ Normalize name (VERY IMPORTANT)
        normalized_department_name = payload.name.strip().lower()
        normalized_department_code = payload.code.strip().lower()
        normalized_department_type= payload.type.strip().lower()

        # 5️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        existing = await FacilityDepartment.find_one({
            "facility_id.$id": facility.id,
            "department_search": normalized_department_name,
            "code_search": normalized_department_code,
            # "is_deleted": False
        })
        if existing:
            raise HTTPException(
                status_code=400,
                detail="department with this name or code already exists in this facility"
            )

        # 6️⃣ Random encryption (actual storage)
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "department_code": payload.code,
                "department_name": payload.name,
                "department_type": payload.type,
                "department_desc": payload.description,
            }
        )
        # 7️⃣ Create Department document
        dept_doc = FacilityDepartment(
            code_search = normalized_department_code,
            department_search = normalized_department_name,
            type_search = normalized_department_type,
            code=encrypted["department_code"],
            department_name=encrypted["department_name"],
            type=encrypted["department_type"],
            description=encrypted["department_desc"],
            facility_id=facility,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await dept_doc.insert()

        # Audit log
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Facility Department",
                resource_id=str(dept_doc.id),
                status="success",
                notes="Facility department created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "facility_department_id": str(dept_doc.id),
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility department"
        )


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return decrypted_raw




@router.get("/list/")
async def get_all_campus_blocks(
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
            FacilityDepartment.created_by.id == user.id,
            FacilityDepartment.is_deleted == False
        ]

        if status:
            conditions.append(FacilityDepartment.status == status.lower())

        
        if search:
            search_value = search.lower()
            conditions.append(
                Or(
                    RegEx(FacilityDepartment.department_search, f"^{search_value}"),
                    RegEx(FacilityDepartment.code_search, f"^{search_value}"),
                    RegEx(FacilityDepartment.type_search, f"^{search_value}")
                )
            )

        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------
        facility_department = await (
            FacilityDepartment.find(
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
        total = await FacilityDepartment.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------
        result = []
        for dept in facility_department:
            result.append({
                "id": str(dept.id),
                "department_name": decrypt_value(ce, dept.department_name),
                "department_code": decrypt_value(ce, dept.code),
                "department_type": decrypt_value(ce, dept.type),
                "facility_id": str(dept.facility_id.id) if dept.facility_id else None,
                "facility_name": (
                    dept.facility_id.facility_name_search
                    if dept.facility_id else None
                ),
                "status": dept.status,
                "created_at": dept.created_at,
                "updated_at": dept.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Facility Department",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Department fetched | "
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




@router.get("/get/department/{facility_id}/")
async def get_facility_departments(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    page : int = Query(1, ge=1),
    page_size : int = Query(10, ge=1),
    search: str | None = Query(None, description="Search by code or department name"),
):
    # ---------------- User ----------------
    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ---------------- Facility ----------------
    try:
        facility_obj = await Facility.get(PydanticObjectId(facility_id))
    except Exception:
        facility_obj = await Facility.get(facility_id)

    if not facility_obj:
        raise HTTPException(status_code=404, detail="Facility not found")

    # ---------------- Encryption ----------------
    
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    # ---------------- Departments (facility + created_by) ----------------
    departments = await FacilityDepartment.find(
        FacilityDepartment.facility_id.id == facility_obj.id,
        FacilityDepartment.created_by.id == user.id
    ).sort("created_at").to_list()
    search_lower = search.lower() if search else None

    # ---------------- Response ----------------
    result = []
    for dep in departments:
        code = _decrypt_value(ce, dep.code)
        department_name = _decrypt_value(ce, dep.department_name)
        if search_lower:
            if (
                search_lower not in str(code or "").lower()
                and search_lower not in str(department_name or "").lower()
            ):
                continue    

        result.append({
            "id": str(dep.id),
            "code": _decrypt_value(ce, dep.code),
            "department_name": _decrypt_value(ce, dep.department_name),
            "type": _decrypt_value(ce, dep.type),
            "description": _decrypt_value(ce, dep.description),
            "created_at": dep.created_at,
            "updated_at": dep.updated_at,
        })

    total = len(result)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_docs = result[start:end]
    # ---------------- Audit ----------------
    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Facility Department",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Facility departments fetched successfully",
        )
    except Exception:
        pass

    
    return {
        "items": paginated_docs,
        "pagination" : {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": (total + page_size - 1) // page_size,
        }
    }


@router.put("/update/department/{department_id}/")
async def update_facility_department(
    department_id: str,
    department: DepartmentSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce
    dek_id = getattr(request.app, "dek_id", None)
    if dek_id is None:
        dek_id = ensure_data_key()
        request.app.dek_id = dek_id

    def enc_det_or_none(val):
        return encrypt_value_deterministic(ce, dek_id, val) if val is not None else None

    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        dept_obj_id = PydanticObjectId(department_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Department ID format")

    dept_doc = await FacilityDepartment.get(dept_obj_id)
    if not dept_doc:
        raise HTTPException(status_code=404, detail="Department not found")

    current_code = _decrypt_value(ce, dept_doc.code)
    current_name = _decrypt_value(ce, dept_doc.department_name)
    current_type = _decrypt_value(ce, dept_doc.type)
    current_desc = _decrypt_value(ce, dept_doc.description)

    new_code = department.code if department.code is not None else current_code
    new_name = department.name if department.name is not None else current_name
    new_type = (department.type.value if department.type else None) if department.type is not None else current_type
    new_desc = department.description if department.description is not None else current_desc

    if new_code is None and new_name is None and new_type is None and new_desc is None:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    dept_doc.code = enc_det_or_none(new_code)
    dept_doc.department_name = enc_det_or_none(new_name)
    dept_doc.type = enc_det_or_none(new_type)
    dept_doc.description = enc_det_or_none(new_desc)
    dept_doc.updated_at = datetime.now(timezone.utc)
    await dept_doc.save()

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Update",
            resource="Facility Department",
            resource_id=str(dept_doc.id),
            status="success",
            notes="Facility department updated successfully",
        )
    except Exception:
        pass

    return {
        "success": True,
        "id": str(dept_doc.id),
        "code": new_code,
        "department_name": new_name,
        "type": new_type,
        "description": new_desc,
        "updated_at": dept_doc.updated_at,
    }




