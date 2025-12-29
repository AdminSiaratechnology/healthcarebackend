from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.transport_vendor import TransportVendorSchema
from beanie import PydanticObjectId
import json
import os
from app.facility.models.transport_vendor import TransportVendorDocs

router = APIRouter(prefix="/facility", tags=["Facility"])


def _decrypt_value(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw


@router.post("/transport-vendor/create/{facility_id}/")
async def create_transport_vendor(
    facility_id: str,
    payload: TransportVendorSchema,
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

        enc_vendor = encrypt_value(ce, dek_id, payload.vendor_name) if payload.vendor_name is not None else None
        enc_contact = encrypt_value(ce, dek_id, payload.contact_number) if payload.contact_number is not None else None

        doc = TransportVendorDocs(
            facility_id=facility,
            vendor_name=enc_vendor,
            contact_number=enc_contact,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await doc.insert()

        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Create",
            resource="Transport Vendor",
            resource_id=str(doc.id),
            status="success",
            notes="Transport vendor created",
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
                resource="Transport Vendor",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/transport-vendor/get/{facility_id}/")
async def get_transport_vendors(
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

        # ---------------- Transport Vendor  ----------------
        transport_vendor = await TransportVendorDocs.find(
            TransportVendorDocs.facility_id.id == facility_obj.id,
            TransportVendorDocs.created_by.id == user.id
        ).sort("-created_at").to_list()


        # ---------------- RESPONSE ----------------
        
       

        result = [
            {
                "id": str(tv.id),
                "vendor_name": _decrypt_value(ce, tv.vendor_name),
                "contact_number": _decrypt_value(ce, tv.contact_number),
                "created_at": tv.created_at,
                "updated_at": tv.updated_at,
            } for tv in transport_vendor
        ]

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Transport Vendor",
                resource_id=str(facility_obj.id),
                status="success",
                notes="Transport vendors fetched",
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
                resource="Transport Vendor",
                resource_id=facility_id,
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
