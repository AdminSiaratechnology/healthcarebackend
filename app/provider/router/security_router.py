from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import ValidationError, BaseModel
from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.provider.security import SecuritySchema
from beanie import PydanticObjectId
import json
import os
from app.provider.models.security import Security
from app.provider.models.providers import Provider

router = APIRouter(prefix="/provider", tags=["Providers"])

class SecurityCreateRequest(BaseModel):
    provider_id: str
    security: SecuritySchema

def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except Exception:
            pass
    if isinstance(raw, str):
        lower = raw.strip().lower()
        if lower in {"true", "1", "yes"}:
            return True
        if lower in {"false", "0", "no"}:
            return False
    return raw

@router.post("/security")
async def create_security(
    payload: SecurityCreateRequest,
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
            prov_oid = PydanticObjectId(payload.provider_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid provider_id")
        provider = await Provider.get(prov_oid)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        role_val = None
        if user.role is not None:
            try:
                r = decrypt_value(ce, user.role)
                role_val = r.decode("utf-8") if isinstance(r, (bytes, bytearray)) else r
            except Exception:
                role_val = None
        is_admin = role_val in {"admin", "super_admin"}
        if not is_admin and provider.user_id != str(user.id):
            raise HTTPException(status_code=403, detail="Forbidden")

        sec = payload.security
        enc_active = encrypt_value(ce, dek_id, sec.is_account_active) if sec.is_account_active is not None else None
        enc_sms = encrypt_value(ce, dek_id, sec.is_sms_authentication) if getattr(sec, "is_sms_authentication", None) is not None else None

        doc = Security(
            provider_id=provider,
            is_account_active=enc_active,
            is_sms_authentication=enc_sms,
            created_by=user,
        )
        await doc.insert()

        await log_audit(
            request=request,
            user_id=current_user_id,
            action="CREATE",
            resource="security",
            resource_id=str(doc.id),
            status="success",
            notes="Security created",
        )

        return {"id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="CREATE",
            resource="security",
            resource_id="N/A",
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/security/{provider_id}")
async def get_security(
    provider_id: str,
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
            prov_oid = PydanticObjectId(provider_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid provider_id")
        provider = await Provider.get(prov_oid)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        role_val = None
        if user.role is not None:
            try:
                r = decrypt_value(ce, user.role)
                role_val = r.decode("utf-8") if isinstance(r, (bytes, bytearray)) else r
            except Exception:
                role_val = None
        is_admin = role_val in {"admin", "super_admin"}
        if not is_admin and provider.user_id != str(user.id):
            raise HTTPException(status_code=403, detail="Forbidden")

        doc = await Security.find_one(Security.provider_id.id == provider.id)
        if not doc:
            raise HTTPException(status_code=404, detail="Security not found")

        return {
            "id": str(doc.id),
            "provider_id": str(provider.id),
            "is_account_active": _decrypt_value(ce, doc.is_account_active),
            "is_sms_authentication": _decrypt_value(ce, doc.is_sms_authentication),
        }
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="READ",
            resource="security",
            resource_id=provider_id,
            status="failed",
            notes=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))
