from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption
from app.utils.audit import log_audit
from app.schemas.facilities.laboratory import LaboratorySchema
from beanie import PydanticObjectId
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


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return decrypted_raw


@router.get("/get/laboratory/{facility_id}/")
async def get_laboratories(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    facility_obj = None
    try:
        facility_obj_id = PydanticObjectId(facility_id)
        facility_obj = await Facility.get(facility_obj_id)
    except Exception:
        pass

    if facility_obj is None:
        facility_obj = await Facility.get(facility_id)
    if not facility_obj:
        raise HTTPException(status_code=404, detail="Facility not found")

    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    # ---------------- Laboratory  ----------------
    laboratory = await Laboratory.find(
        Laboratory.facility_id.id == facility_obj.id,
        Laboratory.created_by.id == user.id
    ).sort("-created_at").to_list()
   
   

    result = [
        {
            "id": str(lb.id),
            "laboratory_name": _decrypt_value(ce, lb.laboratory_name),
            "phone": _decrypt_value(ce, lb.phone),
            "fax": _decrypt_value(ce, lb.fax),
            "pickup_schedule": _decrypt_value(ce, lb.pickup_schedule),
            "interface_type": _decrypt_value(ce, lb.interface_type),
            "loinc_policy": _decrypt_value(ce, lb.loinc_policy),
            "created_at": lb.created_at,
            "updated_at": lb.updated_at,
        } for lb in laboratory
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Laboratory",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Laboratories fetched successfully",
        )
    except Exception:
        pass

    return result


@router.put("/update/laboratory/{laboratory_id}/")
async def update_laboratory(
    laboratory_id: str,
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

        laboratory = await Laboratory.get(PydanticObjectId(laboratory_id))
        if not laboratory:
            raise HTTPException(status_code=404, detail="Laboratory not found")

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        laboratory.laboratory_name = enc_or_none(lab.laboratory_name)
        laboratory.phone = enc_or_none(lab.phone)
        laboratory.fax = enc_or_none(lab.fax)
        laboratory.pickup_schedule = enc_or_none(lab.pickup_schedule)
        laboratory.interface_type = enc_or_none(lab.interface_type)
        laboratory.loinc_policy = enc_or_none(lab.loinc_policy)
        laboratory.updated_at = datetime.now(timezone.utc)

        await laboratory.save()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Laboratory",
                resource_id=str(laboratory.id),
                status="success",
                notes="Laboratory updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "laboratory_id": str(laboratory.id),
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating laboratory"
        )   
