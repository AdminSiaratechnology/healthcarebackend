from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.charge_nurse import ChargeNursesSchema
from beanie import PydanticObjectId

import json
import os
from app.facility.models.facility_chargenurse import ChargeNursesDoc

router = APIRouter(prefix="/facility", tags=["Facility"])


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw


@router.post("/charge-nurse/create/{facility_id}/")
async def create_charge_nurse(
    facility_id: str,
    payload: ChargeNursesSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
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
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")

        facility = await Facility.get(facility_obj_id)
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        enc_name = encrypt_value(ce, dek_id, payload.name) if payload.name else None
        enc_unit = encrypt_value(ce, dek_id, payload.unit) if payload.unit else None
        enc_phone = encrypt_value(ce, dek_id, payload.phone) if payload.unit else None
        # phone is optional in model; schema doesn't include it, so skip unless provided later

        doc = ChargeNursesDoc(
            facility_id=facility,
            name=enc_name,
            unit=enc_unit,
            phone=enc_phone,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await doc.insert()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Create",
            resource="Charge Nurse",
            resource_id=str(doc.id),
            status="success",
            notes="Charge nurse created",
        )

        return {"status": "success","id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Create",
                resource="Charge Nurse",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


# @router.get("/charge-nurse/get/{facility_id}/")
# async def get_charge_nurses(
#     facility_id: str,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce

#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         facility_obj = None
#         try:
#             facility_obj_id = PydanticObjectId(facility_id)
#             facility_obj = await Facility.get(facility_obj_id)
#         except Exception:
#             pass

#         if facility_obj is None:
#             facility_obj = await Facility.get(facility_id)
#         if not facility_obj:
#             raise HTTPException(status_code=404, detail="Facility not found")

#         by_link = await ChargeNursesDoc.find(ChargeNursesDoc.facility_id.id == facility_obj.id).to_list()
#         by_str = await ChargeNursesDoc.find(ChargeNursesDoc.facility_id == str(facility_obj.id)).to_list()

#         seen = set()
#         docs = []
#         for d in by_link + by_str:
#             if str(d.id) in seen:
#                 continue
#             seen.add(str(d.id))
#             docs.append(d)

#         result = [
#             {
#                 "id": str(cn.id),
#                 "name": _decrypt_value(ce, cn.name),
#                 "unit": _decrypt_value(ce, cn.unit),
#                 "phone": _decrypt_value(ce, cn.phone),
#                 "created_at": cn.created_at,
#                 "updated_at": cn.updated_at,
#             } for cn in docs
#         ]

#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Read",
#                 resource="Charge Nurse",
#                 resource_id=str(facility_obj.id),
#                 status="success",
#                 notes="Charge nurses fetched",
#             )
#         except Exception:
#             pass

#         return result
#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=current_user_id,
#                 action="Read",
#                 resource="Charge Nurse",
#                 resource_id=facility_id,
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail=str(e))


@router.get("/charge-nurse/get/{facility_id}/")
async def get_charge_nurses(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    # ---------------- USER ----------------
    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ---------------- FACILITY ----------------
    try:
        facility = await Facility.get(PydanticObjectId(facility_id))
    except Exception:
        facility = await Facility.get(facility_id)

    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")

    # ---------------- ENCRYPTION ----------------
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    # ---------------- CHARGE NURSES (facility + created_by) ----------------
    charge_nurses = await ChargeNursesDoc.find(
        ChargeNursesDoc.facility_id.id == facility.id,
        ChargeNursesDoc.created_by.id == user.id
    ).sort("-created_at").to_list()

    # ---------------- RESPONSE ----------------
    result = []
    for cn in charge_nurses:
        result.append({
            "id": str(cn.id),
            "name": _decrypt_value(ce, cn.name),
            "unit": _decrypt_value(ce, cn.unit),
            "phone": _decrypt_value(ce, cn.phone),
            "created_at": cn.created_at,
            "updated_at": cn.updated_at,
        })

    # ---------------- AUDIT ----------------
    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Charge Nurse",
            resource_id=str(facility.id),
            status="success",
            notes="Charge nurses fetched successfully",
        )
    except Exception:
        pass

    return result
