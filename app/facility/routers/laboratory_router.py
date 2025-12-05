from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value
from app.utils.audit import log_audit
from app.schemas.facilities.laboratory import LaboratorySchema
from beanie import PydanticObjectId

import json
import os
from app.facility.models.laboratory import Laboratory

router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/laboratory/{facility_id}/")
async def create_laboratory(
    facility_id: str,
    lab: LaboratorySchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        client_encryption = request.app.client_encryption
        dek_id = request.app.dek_id

        def enc_or_none(val):
            if val is None:
                return None
            if hasattr(val, "value"):
                val = val.value
            return encrypt_value(client_encryption, dek_id, val)

        try:
            facility_obj_id = PydanticObjectId(facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")

        facility = await Facility.get(facility_obj_id)
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        lab_doc = Laboratory(
            facility_id=facility,
            laboratory_name=enc_or_none(lab.laboratory_name),
            phone=enc_or_none(lab.phone),
            fax=enc_or_none(lab.fax),
            pickup_schedule=enc_or_none(lab.pickup_schedule),
            interface_type=enc_or_none(lab.interface_type),
            loinc_policy=enc_or_none(lab.loinc_policy),
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await lab_doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Laboratory",
                resource_id=str(lab_doc.id),
                status="success",
                notes="Laboratory created successfully",
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
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating laboratory"
        )
