from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value
from app.utils.audit import log_audit
from app.schemas.facilities.key_contacts import KeyContacts
from beanie import PydanticObjectId

import json
import os
from app.facility.models.keycontact import KeyContact

router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/keycontacts/{facility_id}/")
async def create_key_contacts(
    facility_id: str,
    contacts: KeyContacts,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        client_encryption = request.app.client_encryption
        dek_id = request.app.dek_id

        def enc_json_or_none(obj):
            return (
                encrypt_value(client_encryption, dek_id, json.dumps(obj.model_dump()))
                if obj is not None else None
            )

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

        kc_doc = KeyContact(
            facility_id=facility,
            director_of_nursing_and_administrator=enc_json_or_none(contacts.director_of_nursing_and_administrator),
            medical_director=enc_json_or_none(contacts.medical_director),
            admission_coordinator=enc_json_or_none(contacts.admission_coordinator),
            it_administrator=enc_json_or_none(contacts.it_administrator),
            charge_nurse=enc_json_or_none(contacts.charge_nurse),
            emergency_contact=enc_json_or_none(contacts.emergency_contact),
            created_by=user,
        )

        await kc_doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Key Contacts",
                resource_id=str(kc_doc.id),
                status="success",
                notes="Key contacts created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "key_contacts_id": str(kc_doc.id),
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating key contacts"
        )
