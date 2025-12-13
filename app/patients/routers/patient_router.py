from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key, encrypt_value_deterministic
from app.auth.password import hash_password
from app.accounts.models.user import UserRole
from app.utils.audit import log_audit
from app.schemas.patients.personal import PersonalInfo,ContactInformation
from beanie import PydanticObjectId
import json
import os
from app.patients.models.patients import PatientDoc

router = APIRouter(prefix="/patient", tags=["Patients"])


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw


@router.post("/create/")
async def create_patient(
    personal: PersonalInfo,
    contact: ContactInformation,
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

        if not getattr(personal, "facility_id", None):
            raise HTTPException(status_code=400, detail="facility_id is required in body")
        try:
            fac_oid = PydanticObjectId(personal.facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")
        facility = await Facility.get(fac_oid)
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        phone = _decrypt_value(ce, user.phone)
        email = _decrypt_value(ce, user.email)

        personal_data = personal.model_dump(mode="json", serialize_as_any=True)
        contact_input = contact.model_dump(mode="json", serialize_as_any=True) if contact else {}
        if not contact_input.get("phone_number"):
            contact_input["phone_number"] = phone
        if not contact_input.get("email"):
            contact_input["email"] = email

        full_name = " ".join([p for p in [personal.first_name, personal.middle_name, personal.last_name] if p]).strip() or (personal.preferred_name or "Patient")
        enc_full_name = encrypt_value(ce, dek_id, full_name)
        enc_email = encrypt_value_deterministic(ce, dek_id, contact_input.get("email")) if contact_input.get("email") else None
        enc_phone = encrypt_value_deterministic(ce, dek_id, contact_input.get("phone_number")) if contact_input.get("phone_number") else None
        enc_role_user = encrypt_value(ce, dek_id, UserRole.PATIENT.value)
        enc_password = encrypt_value(ce, dek_id, hash_password(contact_input.get("password"))) if contact_input.get("password") else None

        patient_user = UserDoc(
            full_name=enc_full_name,
            email=enc_email,
            phone=enc_phone,
            role=enc_role_user,
            password=enc_password,
            is_active=True,
        )
        await patient_user.insert()

        payload = {
            "personal": personal_data,
            "contact": contact_input,
        }
        enc_info = encrypt_value(ce, dek_id, json.dumps(payload))

        doc = PatientDoc(
            facility_id=facility,
            user_id=patient_user,
            personal_information=enc_info,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await doc.insert()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Create",
            resource="Patient",
            resource_id=str(doc.id),
            status="success",
            notes="Patient created",
        )

        return {"id": str(doc.id), "user_id": str(patient_user.id)}
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Create",
            resource="Patient",
            resource_id="N/A",
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get/{facility_id}/")
async def get_patients(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        fac_obj = None
        try:
            fac_oid = PydanticObjectId(facility_id)
            fac_obj = await Facility.get(fac_oid)
        except Exception:
            pass
        if fac_obj is None:
            fac_obj = await Facility.get(facility_id)
        if not fac_obj:
            raise HTTPException(status_code=404, detail="Facility not found")

        by_link = await PatientDoc.find(PatientDoc.facility_id.id == fac_obj.id).to_list()
        by_str = await PatientDoc.find(PatientDoc.facility_id == str(fac_obj.id)).to_list()

        seen = set()
        docs = []
        for d in by_link + by_str:
            if str(d.id) in seen:
                continue
            seen.add(str(d.id))
            docs.append(d)

        result = []
        for p in docs:
            raw = _decrypt_value(ce, p.personal_information)
            info = {}
            try:
                info = json.loads(raw) if isinstance(raw, str) else {}
            except Exception:
                info = {}
            result.append({
                "id": str(p.id),
                "personal": info.get("personal"),
                "contact": info.get("contact"),
                "created_at": p.created_at,
                "updated_at": p.updated_at,
            })

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Patient",
            resource_id=str(fac_obj.id),
            status="success",
            notes="Patients fetched",
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Read",
            resource="Patient",
            resource_id=facility_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))
