from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms
from app.facility.models.beds import Beds
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key, encrypt_value_deterministic
from app.auth.password import hash_password
from app.accounts.models.user import UserRole
from app.utils.audit import log_audit
from app.schemas.patients.admissons import PatientAdmissionSchema
from beanie import PydanticObjectId
import json
import os
from app.patients.models.patients import PatientDoc
from app.patients.models.admissons import PatientAdmissionDoc

router = APIRouter(prefix="/patient", tags=["Patients"])


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw


@router.post("/admission/create/{patient_id}/")
async def create_patient_admission(
    patient_id: str,
    payload: PatientAdmissionSchema,
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

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        try:
            p_oid = PydanticObjectId(patient_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Patient ID format")
        patient = await PatientDoc.get(p_oid)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        try:
            room_oid = PydanticObjectId(payload.room_id)
            room = await FacilityRooms.get(room_oid)
        except Exception:
            room = await FacilityRooms.get(payload.room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        try:
            bed_oid = PydanticObjectId(payload.bed_id)
            bed = await Beds.get(bed_oid)
        except Exception:
            bed = await Beds.get(payload.bed_id)
        if not bed:
            raise HTTPException(status_code=404, detail="Bed not found")

        enc_admission_date = encrypt_value(ce, dek_id, payload.admission_date.isoformat()) if payload.admission_date else None
        enc_admission_location = encrypt_value(ce, dek_id, payload.admission_location) if payload.admission_location else None
        enc_resident_number = encrypt_value(ce, dek_id, payload.resident_number) if payload.resident_number else None
        enc_admission_type = encrypt_value(ce, dek_id, payload.admission_type.value) if payload.admission_type else None
        # status in schema is Enum; store textual value
        enc_status = encrypt_value(ce, dek_id, getattr(payload.status, "value", str(payload.status))) if payload.status else None
        enc_admitted_form = encrypt_value(ce, dek_id, payload.admitted_form.value) if payload.admitted_form else None
        enc_from_date = encrypt_value(ce, dek_id, payload.from_date.isoformat()) if payload.from_date else None
        enc_to_date = encrypt_value(ce, dek_id, payload.to_date.isoformat()) if payload.to_date else None

        doc = PatientAdmissionDoc(
            patient_id=patient,
            admission_date=enc_admission_date,
            room_id=room,
            bed_id=bed,
            admission_location=enc_admission_location,
            resident_number=enc_resident_number,
            admission_type=enc_admission_type,
            status=enc_status,
            admitted_form=enc_admitted_form,
            from_date=enc_from_date,
            to_date=enc_to_date,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await doc.insert()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Create",
            resource="Patient Admission",
            resource_id=str(doc.id),
            status="success",
            notes="Patient admission created",
        )

        return {"id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Create",
            resource="Patient Admission",
            resource_id="N/A",
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admission/get/{patient_id}/")
async def get_patient_admissions(
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
        patient = await PatientDoc.get(p_oid)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        
        pat_doc = await PatientAdmissionDoc.find(
        PatientAdmissionDoc.patient_id.id == patient.id,
        PatientAdmissionDoc.created_by.id == user.id
        ).to_list()

      
       
       
        result = []
        for a in pat_doc:
            result.append({
                "id": str(a.id),
                "admission_date": _decrypt_value(ce, a.admission_date),
                "room_id": str(a.room_id.ref.id),
                "bed_id": str(a.bed_id.ref.id),
                "admission_location": _decrypt_value(ce, a.admission_location),
                "resident_number": _decrypt_value(ce, a.resident_number),
                "admission_type": _decrypt_value(ce, a.admission_type),
                "status": _decrypt_value(ce, a.status),
                "admitted_form": _decrypt_value(ce, a.admitted_form),
                "from_date": _decrypt_value(ce, a.from_date),
                "to_date": _decrypt_value(ce, a.to_date),
                "created_at": a.created_at,
                "updated_at": a.updated_at,
            })

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Patient Admission",
            resource_id=str(patient.id),
            status="success",
            notes="Admissions fetched",
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Read",
            resource="Patient Admission",
            resource_id=patient_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))



@router.put("/admission/update/{admission_id}/")
async def update_patient_admission(
    admission_id: str,
    payload: PatientAdmissionSchema,
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

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        try:
            adm_oid = PydanticObjectId(admission_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Admission ID format")
        admission = await PatientAdmissionDoc.get(adm_oid)
        if not admission:
            raise HTTPException(status_code=404, detail="Patient Admission not found")
        
        room_oid = PydanticObjectId(payload.room_id)
        room = await FacilityRooms.get(room_oid)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        bed_oid = PydanticObjectId(payload.bed_id)
        bed = await Beds.get(bed_oid)
        if not bed:
            raise HTTPException(status_code=404, detail="Bed not found")

        # Update fields if provided
        if payload.admission_date is not None:
            admission.admission_date = encrypt_value(ce, dek_id, payload.admission_date.isoformat())
        if payload.admission_location is not None:
            admission.admission_location = encrypt_value(ce, dek_id, payload.admission_location)
        if payload.resident_number is not None:
            admission.resident_number = encrypt_value(ce, dek_id, payload.resident_number)
        if payload.admission_type is not None:
            admission.admission_type = encrypt_value(ce, dek_id, payload.admission_type.value)
        if payload.status is not None:
            admission.status = encrypt_value(ce, dek_id, getattr(payload.status, "value", str(payload.status)))
        if payload.admitted_form is not None:
            admission.admitted_form = encrypt_value(ce, dek_id, payload.admitted_form.value)
        if payload.from_date is not None:
            admission.from_date = encrypt_value(ce, dek_id, payload.from_date.isoformat())
        if payload.to_date is not None:
            admission.to_date = encrypt_value(ce, dek_id, payload.to_date.isoformat())
        
        admission.room_id = room
        admission.bed_id = bed

        admission.updated_at = datetime.now(timezone.utc)
        await admission.save()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Update",
            resource="Patient Admission",
            resource_id=str(admission.id),
            status="success",
            notes="Patient admission updated",
        )
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:  
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="Update",
            resource="Patient Admission",
            resource_id=admission_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))