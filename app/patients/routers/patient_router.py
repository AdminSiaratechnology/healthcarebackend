from datetime import datetime, timezone, date
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
from app.schemas.patients.personal import PatientSchema, PersonalInfo, ContactInformation
from app.provider.models.providers import Provider
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

def _decrypt_json_field(client_encryption, encrypted_val):
    val = _decrypt_value(client_encryption, encrypted_val)
    if not val:
        return None
    try:
        return json.loads(val) if isinstance(val, str) else val
    except Exception:
        return None


@router.post("/create/{facility_id}/")
async def create_patient(
    facility_id: str,
    schema: PatientSchema,
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

        fac_obj = None
        try:
            fac_oid = PydanticObjectId(facility_id)
            fac_obj = await Facility.get(fac_oid)
        except Exception:
            pass
        if fac_obj is None:
            fac_obj = await Facility.get(facility_id)
        facility = fac_obj
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        phone = _decrypt_value(ce, user.phone)
        email = _decrypt_value(ce, user.email)

        raw_body = {}
        try:
            raw_body = await request.json()
        except Exception:
            raw_body = {}
        personal_data = schema.personal_information.model_dump(mode="json", serialize_as_any=True) if schema.personal_information else {}
        if not personal_data:
            pi_alt = raw_body.get("personal") or raw_body.get("personal_information") or {}
            if isinstance(pi_alt, dict):
                personal_data = pi_alt
        
        contact_input = schema.contact_information.model_dump(mode="json", serialize_as_any=True) if schema.contact_information else {}
        if not contact_input:
            ci_alt = raw_body.get("contact") or raw_body.get("contact_information") or {}
            if isinstance(ci_alt, dict):
                contact_input = ci_alt
        if not contact_input.get("phone_number"):
            contact_input["phone_number"] = phone
        if not contact_input.get("email"):
            contact_input["email"] = email             

        pi = schema.personal_information
        name_parts = []
        if pi:
            for p in [pi.first_name, pi.middle_name, pi.last_name]:
                if p:
                    name_parts.append(p)
        else:
            for p in [personal_data.get("first_name"), personal_data.get("middle_name"), personal_data.get("last_name")]:
                if p:
                    name_parts.append(p)
        preferred = pi.preferred_name if pi and getattr(pi, "preferred_name", None) else personal_data.get("preferred_name")
        full_name = " ".join(name_parts).strip() or (preferred or "Patient")
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

        provider_obj = None
        if schema.provider_id:
            try:
                prov_oid = PydanticObjectId(schema.provider_id)
                provider_obj = await Provider.get(prov_oid)
            except Exception:
                provider_obj = await Provider.get(schema.provider_id)

        doc = PatientDoc(
            facility_id=facility,
            provider_id=provider_obj,
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

        return {"id": str(doc.id), "user_id": str(patient_user.id), "provider_id": str(provider_obj.id) if provider_obj else None}
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

@router.get("/get/{patient_id}/")
async def get_patient(
    patient_id: str,
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

        try:
            p_oid = PydanticObjectId(patient_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Patient ID format")
        doc = await PatientDoc.get(p_oid)
        if not doc:
            raise HTTPException(status_code=404, detail="Patient not found")
        

        
        fac_id = None
        if doc.facility_id:
            try:
                fac_doc = await doc.facility_id.fetch()
                fac_id = str(fac_doc.id)
            except Exception:
                try:
                    fac_id = str(getattr(doc.facility_id, "id"))
                except Exception:
                    fac_id = None

        prov_id = None
        if doc.provider_id:
            try:
                prov_doc = await doc.provider_id.fetch()
                prov_id = str(prov_doc.id)
            except Exception:
                try:
                    prov_id = str(getattr(doc.provider_id, "id"))
                except Exception:
                    prov_id = None

        usr_id = None
        if doc.user_id:
            try:
                usr_doc = await doc.user_id.fetch()
                usr_id = str(usr_doc.id)
            except Exception:
                try:
                    usr_id = str(getattr(doc.user_id, "id"))
                except Exception:
                    usr_id = None

        personal_payload = _decrypt_json_field(ce, doc.personal_information)
        print("sooooooooooooooooooooooooooooooo",personal_payload)
        personal_info = (personal_payload or {}).get("personal") or {}
        contact_info = (personal_payload or {}).get("contact") or {}

        if not personal_info and doc.user_id:
            try:
                udoc = await doc.user_id.fetch()
                display_name = _decrypt_value(ce, udoc.full_name)
                if display_name:
                    personal_info = {"preferred_name": display_name}
            except Exception:
                pass

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Patient",
            resource_id=str(doc.id),
            status="success",
            notes="Patient fetched",
        )

        try:
            pi_model = PersonalInfo.model_validate(personal_info)
            print("gggggggggggggggggggggggggggg",pi_model)
        except ValidationError:
            _d = {
                "first_name": personal_info.get("first_name"),
                "middle_name": personal_info.get("middle_name"),
                "last_name": personal_info.get("last_name"),
                "preferred_name": personal_info.get("preferred_name"),
                "maiden_name": personal_info.get("maiden_name"),
                "birth_place": personal_info.get("birth_place"),
                "dob": None,
                "gender": personal_info.get("gender"),
                "race": personal_info.get("race"),
                "primary_language": personal_info.get("primary_language"),
                "marital_status": personal_info.get("marital_status"),
                "religion": personal_info.get("religion"),
            }
            _dob_val = personal_info.get("dob")
            if isinstance(_dob_val, str):
                try:
                    _d["dob"] = date.fromisoformat(_dob_val)
                except Exception:
                    _d["dob"] = None
            elif isinstance(_dob_val, date):
                _d["dob"] = _dob_val
            if not _d.get("preferred_name") and doc.user_id:
                try:
                    _udoc = await doc.user_id.fetch()
                    _name = _decrypt_value(ce, _udoc.full_name)
                    if _name:
                        _d["preferred_name"] = _name
                except Exception:
                    pass
            pi_model = PersonalInfo.model_construct(**_d)
        ci_model = ContactInformation.model_validate(contact_info)

        return {
            "id": str(doc.id),
            "facility_id": fac_id,
            "provider_id": prov_id,
            "user_id": usr_id,
            "personal_information": pi_model.model_dump(mode="json", serialize_as_any=True),
            "contact_information": ci_model.model_dump(mode="json", serialize_as_any=True),
            "created_at": doc.created_at,
            "updated_at": doc.updated_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Read",
            resource="Patient",
            resource_id=patient_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list/")
async def list_patients(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    search: str = "",
    page: int = 1,
    limit: int = 10,
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        by_link = await PatientDoc.find(PatientDoc.created_by.id == user.id).sort("-created_at").to_list()
        by_str = await PatientDoc.find(PatientDoc.created_by == str(user.id)).sort("-created_at").to_list()

        seen = set()
        docs: list[PatientDoc] = []
        for d in by_link + by_str:
            did = str(getattr(d, "id", ""))
            if not did or did in seen:
                continue
            seen.add(did)
            docs.append(d)

        q = (search or "").strip().lower()
        q_tokens = [t for t in q.split() if t]

        items = []
        for doc in docs:
            full_name = None
            usr_id = None
            if doc.user_id:
                try:
                    usr_doc = await doc.user_id.fetch()
                    usr_id = str(usr_doc.id)
                    full_name = _decrypt_value(ce, getattr(usr_doc, "full_name", None))
                except Exception:
                    try:
                        usr_id = str(getattr(doc.user_id, "id"))
                    except Exception:
                        usr_id = None

            personal_payload = _decrypt_json_field(ce, doc.personal_information) or {}
            personal_info = (personal_payload or {}).get("personal") or {}

            first_name = personal_info.get("first_name")
            middle_name = personal_info.get("middle_name")
            last_name = personal_info.get("last_name")

            if q_tokens:
                blob = " ".join([
                    full_name or "",
                    first_name or "",
                    middle_name or "",
                    last_name or "",
                ]).lower()
                ok = all(t in blob for t in q_tokens)
                if not ok:
                    continue

            fac_id = None
            if doc.facility_id:
                try:
                    fac_doc = await doc.facility_id.fetch()
                    fac_id = str(fac_doc.id)
                except Exception:
                    try:
                        fac_id = str(getattr(doc.facility_id, "id"))
                    except Exception:
                        fac_id = None

            prov_id = None
            if doc.provider_id:
                try:
                    prov_doc = await doc.provider_id.fetch()
                    prov_id = str(prov_doc.id)
                except Exception:
                    try:
                        prov_id = str(getattr(doc.provider_id, "id"))
                    except Exception:
                        prov_id = None

            items.append({
                "id": str(doc.id),
                "facility_id": fac_id,
                "provider_id": prov_id,
                "user_id": usr_id,
                "full_name": full_name,
                "first_name": first_name,
                "middle_name": middle_name,
                "last_name": last_name,
                "created_at": doc.created_at,
                "updated_at": doc.updated_at,
            })

        total = len(items)
        if limit <= 0:
            limit = 10
        if page <= 0:
            page = 1
        start = (page - 1) * limit
        end = start + limit
        page_items = items[start:end]
        pages = (total + limit - 1) // limit

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Patient",
                resource_id=f"list:created_by:{str(user.id)}",
                status="success",
                notes="Patients listed",
            )
        except Exception:
            pass

        return {
            "patients": page_items,
            "page": page,
            "limit": limit,
            "total": total,
            "pages": pages,
        }
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="Read",
                resource="Patient",
                resource_id=f"list:created_by:{current_user_id}",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
