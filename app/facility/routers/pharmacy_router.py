from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value
from app.utils.audit import log_audit
from app.schemas.facilities.pharmacies import PharmaciesSchema
from beanie import PydanticObjectId

import json
import os
from app.facility.models.pharmacies import Pharmacies

router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/pharmacy/{facility_id}/")
async def create_pharmacy(
    facility_id: str,
    pharmacy: PharmaciesSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        client_encryption = request.app.client_encryption
        dek_id = request.app.dek_id

        def enc_or_none(val):
            return encrypt_value(client_encryption, dek_id, val) if val is not None else None

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

        pharmacy_doc = Pharmacies(
            facility_id=facility,
            pharmacy_name=enc_or_none(pharmacy.pharmacy_name),
            phone=enc_or_none(pharmacy.phone),
            address=enc_or_none(pharmacy.address),
            fax=enc_or_none(pharmacy.fax),
            after_hours_phone=enc_or_none(pharmacy.after_hours_phone),
            contract_file_id=enc_or_none(pharmacy.contract_file_id),
            delivery_schedule=enc_or_none(pharmacy.delivery_schedule),
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await pharmacy_doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Pharmacy",
                resource_id=str(pharmacy_doc.id),
                status="success",
                notes="Pharmacy created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "pharmacy_id": str(pharmacy_doc.id),
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating pharmacy"
        )
