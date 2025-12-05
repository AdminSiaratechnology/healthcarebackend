from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.facility.models.facility_department import FacilityDepartment

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value
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
