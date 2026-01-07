from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
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
)
from app.utils.audit import log_audit
from app.schemas.facilities.department import DepartmentSchema
from beanie import PydanticObjectId

import json
import os


router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/department/{facility_id}/")
async def create_facility_department(
    facility_id: str,
    department: DepartmentSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        client_encryption = request.app.client_encryption
        dek_id = request.app.dek_id

        # Encrypt individual fields
        def enc_or_none(val):
            return encrypt_value(client_encryption, dek_id, val) if val is not None else None

        code_enc = enc_or_none(department.code)
        name_enc = enc_or_none(department.name)
        type_enc = enc_or_none(department.type.value if department.type else None)
        desc_enc = enc_or_none(getattr(department, "description", None))

        # Validate Facility ID format
        try:
            facility_obj_id = PydanticObjectId(facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")

        facility = await Facility.get(facility_obj_id)
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        # Validate User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Create Department document
        dept_doc = FacilityDepartment(
            code=code_enc,
            department_name=name_enc,
            type=type_enc,
            description=desc_enc,
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


# @router.get("/get/department/{facility_id}/")
# async def get_facility_departments(
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

#     ce = request.app.client_encryption

#     by_link = await FacilityDepartment.find(FacilityDepartment.facility_id.id == facility_obj.id).to_list()
#     by_str = await FacilityDepartment.find(FacilityDepartment.facility_id == str(facility_obj.id)).to_list()

#     seen = set()
#     docs = []
#     for d in by_link + by_str:
#         if str(d.id) in seen:
#             continue
#         seen.add(str(d.id))
#         docs.append(d)

#     result = [
#         {
#             "id": str(dep.id),
#             "code": _decrypt_value(ce, dep.code),
#             "department_name": _decrypt_value(ce, dep.department_name),
#             "type": _decrypt_value(ce, dep.type),
#             "description": _decrypt_value(ce, dep.description),
#             "created_at": dep.created_at,
#             "updated_at": dep.updated_at,
#         } for dep in docs
#     ]

#     try:
#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Read",
#             resource="Facility Department",
#             resource_id=str(facility_obj.id),
#             status="success",
#             notes="Facility departments fetched successfully",
#         )
#     except Exception:
#         pass

#     return result


@router.get("/get/department/{facility_id}/")
async def get_facility_departments(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
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

    # ---------------- Response ----------------
    result = []
    for dep in departments:
        result.append({
            "id": str(dep.id),
            "code": _decrypt_value(ce, dep.code),
            "department_name": _decrypt_value(ce, dep.department_name),
            "type": _decrypt_value(ce, dep.type),
            "description": _decrypt_value(ce, dep.description),
            "created_at": dep.created_at,
            "updated_at": dep.updated_at,
        })

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

    return result


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




