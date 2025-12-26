from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key, encrypt_value_deterministic
from app.utils.audit import log_audit
from app.schemas.PatientNotes.notes import NotesSchema
from beanie import PydanticObjectId
import json
import os
from app.PatientNotes.models.notes import PatientNotesDoc
from app.patients.models.patients import PatientDoc


router = APIRouter(prefix="/notes", tags=["Notes"])


def _dec_str(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode() if isinstance(raw, (bytes, bytearray)) else raw


@router.post("/create/notes/{patient_id}/")
async def create_notes(
    notes: NotesSchema,
    request: Request,
    patient_id: str,
    current_user_id: str = Depends(get_current_user_id)
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
            pat_doc = await PatientDoc.get(PydanticObjectId(patient_id))

        except Exception:
            pat_doc = None
        if not pat_doc:
            raise HTTPException(status_code=404, detail="Patient not found")
        enc_notes_det = encrypt_value_deterministic(ce, dek_id, notes.notes)
        enc_notes = enc_notes_det
       
        doc = PatientNotesDoc(
            patient_id = pat_doc,
            notes=enc_notes,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await doc.insert()
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Patient Notes",
                resource_id=str(doc.id),
                status="success",
                notes="Notes created",
            )
        except Exception:
            pass
        return {"status" :"success","id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Create",
                resource="Patient Notes",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while creating Patient Notes")



@router.get("/get/notes/{patient_id}/")
async def list_notes(
    request: Request,
    patient_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        pat_doc = await PatientDoc.get(PydanticObjectId(patient_id))
    except Exception:
        pat_doc = None
    if not pat_doc:
        raise HTTPException(status_code=404, detail="Patient not found")
    notes = await PatientNotesDoc.find({"patient_id.$id": pat_doc.id}).to_list()

    items = []
    for n in notes:
        items.append({
            "id": str(n.id),
            "notes": _dec_str(ce, n.notes),
            "created_at": n.created_at,
            "updated_at": n.updated_at,
        })
    
    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Patient Notes",
            resource_id=str(pat_doc.id),
            status="success",
            notes="Patient Notes listed",
        )
    except Exception:
        pass

    return items

