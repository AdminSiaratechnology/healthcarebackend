from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.breach_contact import BreachContactsSchema
from beanie import PydanticObjectId
import json
import os
from app.facility.models.facility_breach_contact import BrachResponseContactDocs


router = APIRouter(prefix="/facility", tags=["Facility"]) 


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw


@router.post("/breach-contact/create/{facility_id}/")
async def create_breach_contact(
    facility_id: str,
    payload: BreachContactsSchema,
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

        enc_name = encrypt_value(ce, dek_id, payload.name) if payload.name is not None else None
        enc_role = encrypt_value(ce, dek_id, payload.Role) if payload.Role is not None else None
        enc_phone = encrypt_value(ce, dek_id, payload.phone) if payload.phone is not None else None
        enc_email = encrypt_value(ce, dek_id, payload.email) if payload.email is not None else None

        doc = BrachResponseContactDocs(
            facility_id=facility,
            name=enc_name,
            Role=enc_role,
            phone=enc_phone,
            email=enc_email,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await doc.insert()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Create",
            resource="Breach Contact",
            resource_id=str(doc.id),
            status="success",
            notes="Breach contact created",
        )

        return {"status":"success","id": str(doc.id)}
        
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Create",
                resource="Breach Contact",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/breach-contact/get/{facility_id}/")
async def get_breach_contacts(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        

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

        # ---------------- ENCRYPTION ----------------
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        # ---------------- Breach Contact  ----------------
        breach_con = await BrachResponseContactDocs.find(
            BrachResponseContactDocs.facility_id.id == facility_obj.id,
            BrachResponseContactDocs.created_by.id == user.id
        ).sort("-created_at").to_list()


        # ---------------- RESPONSE ----------------
        

        result = [
            {
                "id": str(bc.id),
                "name": _decrypt_value(ce, bc.name),
                "Role": _decrypt_value(ce, bc.Role),
                "phone": _decrypt_value(ce, bc.phone),
                "email": _decrypt_value(ce, bc.email),
                "created_at": bc.created_at,
                "updated_at": bc.updated_at,
            } for bc in breach_con
        ]

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Breach Contact",
                resource_id=str(facility_obj.id),
                status="success",
                notes="Breach contacts fetched",
            )
        except Exception:
            pass

        return result
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Read",
                resource="Breach Contact",
                resource_id=facility_id,
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
