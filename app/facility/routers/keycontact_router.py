from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError


from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
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
        client_encryption = getattr(request.app, "client_encryption", None)
        if client_encryption is None:
            client_encryption = init_encryption()
        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()

        def _serialize(obj):
            if obj is None:
                return None
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            if isinstance(obj, list):
                return [(_item.model_dump() if hasattr(_item, "model_dump") else _item) for _item in obj]
            return obj

        def enc_json_or_none(obj):
            return (
                encrypt_value(client_encryption, dek_id, json.dumps(_serialize(obj)))
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

from bson.binary import Binary

def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    import json as _json
    return _json.loads(decrypted_raw)



@router.get("/get/keycontacts/{facility_id}/")
async def get_key_contacts(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
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

    # ---------------- KEY CONTACTS (facility + created_by) ----------------
    key_contacts = await KeyContact.find(
        KeyContact.facility_id.id == facility.id,
        KeyContact.created_by.id == user.id
    ).sort("-created_at").to_list()

    # ---------------- RESPONSE ----------------
    result = []
    for kc in key_contacts:
        result.append({
            "id": str(kc.id),
            "director_of_nursing_and_administrator":
                _decrypt_json_field(ce, kc.director_of_nursing_and_administrator),
            "medical_director":
                _decrypt_json_field(ce, kc.medical_director),
            "admission_coordinator":
                _decrypt_json_field(ce, kc.admission_coordinator),
            "it_administrator":
                _decrypt_json_field(ce, kc.it_administrator),
            "created_at": kc.created_at,
            "updated_at": kc.updated_at,
        })

    # ---------------- AUDIT ----------------
    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Key Contacts",
            resource_id=str(facility.id),
            status="success",
            notes="Key contacts fetched successfully",
        )
    except Exception:
        pass

    return result



@router.put("/update/keycontact/{key_id}")
async def update_key_contact(
    key_id: str,
    contacts: KeyContacts,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    # ---------------- Encryption ----------------
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    dek_id = getattr(request.app, "dek_id", None)
    if dek_id is None:
        dek_id = ensure_data_key()
        request.app.dek_id = dek_id

    def enc_or_none(val):
        return encrypt_value(ce, dek_id, val) if val is not None else None

    # ---------------- User ----------------
    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ---------------- KeyContact ----------------
    try:
        key_obj_id = PydanticObjectId(key_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Key-Contact ID format")

    key_doc = await KeyContact.get(key_obj_id)
    if not key_doc:
        raise HTTPException(status_code=404, detail="Key-Contact not found")

    # 🔒 Ownership check
    # if not key_doc.created_by or key_doc.created_by.id != user.id:
    #     raise HTTPException(status_code=403, detail="Not allowed to update this record")

    # ---------------- Update Data ----------------
    update_data = contacts.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    # ---------------- Apply updates ----------------
    if "director_of_nursing_and_administrator" in update_data:
        key_doc.director_of_nursing_and_administrator = enc_or_none(
            update_data["director_of_nursing_and_administrator"]
        )

    if "medical_director" in update_data:
        key_doc.medical_director = enc_or_none(
            update_data["medical_director"]
        )

    if "admission_coordinator" in update_data:
        key_doc.admission_coordinator = enc_or_none(
            update_data["admission_coordinator"]
        )

    if "it_administrator" in update_data:
        key_doc.it_administrator = enc_or_none(
            update_data["it_administrator"]
        )

    await key_doc.save()

    # ---------------- Audit ----------------
    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Update",
            resource="KeyContact",
            resource_id=str(key_doc.id),
            status="success",
            notes="KeyContact updated successfully",
        )
    except Exception:
        pass

    # ---------------- Response (DECRYPTED) ----------------
    return {
    "success": True,
    "id": str(key_doc.id),
    # "director": safe_dec_json(ce, key_doc.director_of_nursing_and_administrator),
    # "medical_director": safe_dec_json(ce, key_doc.medical_director),
    # "admission_coordinator": safe_dec_json(ce, key_doc.admission_coordinator),
    # "it_administrator": safe_dec_json(ce, key_doc.it_administrator),
    "created_at": key_doc.created_at,
    "updated_at": key_doc.updated_at,
}
