from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.statereportingidentifiers import StateReportingIdentifiersSchema
from beanie import PydanticObjectId
import json
import os
from app.facility.models.state_reporting_identifiers import StateReportingIdentifiersDocs

router = APIRouter(prefix="/facility", tags=["Facility"])


def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return json.loads(decrypted_raw)


@router.post("/create/state-reporting-identifiers/{facility_id}/")
async def create_state_reporting_identifier(
    facility_id: str,
    payload: StateReportingIdentifiersSchema,
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

        def enc_json_or_none(val):
            return (
                encrypt_value(
                    client_encryption,
                    dek_id,
                    json.dumps(val)
                ) if val is not None else None
            )

        doc = StateReportingIdentifiersDocs(
            facility_id=facility,
            registry_system_name=enc_json_or_none(payload.registry_system_name),
            identifier_value=enc_json_or_none(payload.identifier_value),
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
                resource="StateReportingIdentifiers",
                resource_id=str(doc.id),
                status="success",
                notes="State reporting identifier created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "state_reporting_identifier_id": str(doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Create",
                resource="StateReportingIdentifiers",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while creating state reporting identifier")


@router.get("/get/state-reporting-identifiers/{facility_id}/")
async def get_state_reporting_identifiers(
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

    by_link = await StateReportingIdentifiersDocs.find(StateReportingIdentifiersDocs.facility_id.id == facility_obj.id).to_list()
    by_str = await StateReportingIdentifiersDocs.find(StateReportingIdentifiersDocs.facility_id == str(facility_obj.id)).to_list()

    seen = set()
    docs = []
    for d in by_link + by_str:
        if str(d.id) in seen:
            continue
        seen.add(str(d.id))
        docs.append(d)

    result = [
        {
            "id": str(item.id),
            "registry_system_name": _decrypt_json_field(ce, item.registry_system_name),
            "identifier_value": _decrypt_json_field(ce, item.identifier_value),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        } for item in docs
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="StateReportingIdentifiers",
            resource_id=str(facility_obj.id),
            status="success",
            notes="State reporting identifiers fetched successfully",
        )
    except Exception:
        pass

    return result
