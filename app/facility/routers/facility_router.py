from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
# from app.schemas.facility import FacilityPayload

from app.facility.models.facility import Facility
from app.facility.models.facility_branding import FacilityBranding
from app.schemas.facility import FacilityCreate, BrandingInfo, StructureInfo

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value
from app.utils.audit import log_audit
import json
import os
import uuid



router = APIRouter(prefix="/facility", tags=["Facility"])



def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return json.loads(decrypted_raw)


@router.post("")
async def create_facility(
    request: Request,
    payload: FacilityCreate,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        ce = request.app.client_encryption
        dek = request.app.dek_id

        body = json.dumps({
            "basic_info": payload.basic_info.model_dump(),
            "address_info": payload.address_info.model_dump(),
        })

        enc_basic = encrypt_value(ce, dek, body)

        facility = Facility(
            basic=enc_basic,
            created_by=user,
        )
        await facility.insert()

        await log_audit(
            request=request,
            user_id=current_user_id,
            action="CREATE",
            resource="facility",
            resource_id=str(facility.id),
            status="success",
            notes=f"Facility created by {current_user_id}"
        )

        return {
            "id": str(facility.id),
            "created_at": facility.created_at,
            "updated_at": facility.updated_at,
        }
    except HTTPException:
        raise
    except ValidationError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="CREATE",
            resource="facility",
            resource_id="N/A",
            status="failed",
            notes=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))






@router.get("")
async def get_facilities_for_user(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        facilities = await Facility.find(Facility.created_by.id == user.id).to_list()

        ce = request.app.client_encryption
        result = []
        for facility in facilities:
            data = _decrypt_json_field(ce, facility.basic)
            result.append({
                "id": str(facility.id),
                "basic_info": (data or {}).get("basic_info"),
                "address_info": (data or {}).get("address_info"),
                "created_at": facility.created_at,
                "updated_at": facility.updated_at,
            })

        await log_audit(
            request=request,
            user_id=current_user_id,
            action="READ",
            resource="facility",
            resource_id="list",
            status="success",
            notes=f"Facilities fetched by {current_user_id}"
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            action="READ",
            resource="facility",
            resource_id="list",
            status="failed",
            notes=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


# @router.get("/facility")
# async def get_facility_for_creator(request: Request, current_user_id: str = Depends(get_current_user_id)):
#     try:
#         facilities = await Facility.find(Facility.created_by_id == str(current_user_id)).to_list()
#         if not facilities:
#             raise HTTPException(status_code=404, detail="Facility not found")

#         result = []
#         for facility in facilities:
#             ce = request.app.client_encryption
#             basic_doc = await BasicDoc.find_one(BasicDoc.facility.id == facility.id)
#             address_doc = await AddressDoc.find_one(AddressDoc.facility.id == facility.id)
#             contacts_doc = await ContactsDoc.find_one(ContactsDoc.facility.id == facility.id)
#             branding_doc = await BrandingDoc.find_one(BrandingDoc.facility.id == facility.id)
#             structure_doc = await StructureDoc.find_one(StructureDoc.facility.id == facility.id)
#             rooms_beds_doc = await RoomsBedsDoc.find_one(RoomsBedsDoc.facility.id == facility.id)
#             key_contacts_doc = await KeyContactsDoc.find_one(KeyContactsDoc.facility.id == facility.id)
#             partners_doc = await PartnersDoc.find_one(PartnersDoc.facility.id == facility.id)
#             workstations_doc = await WorkstationsDoc.find_one(WorkstationsDoc.facility.id == facility.id)
#             interop_doc = await InteroperabilityDoc.find_one(InteroperabilityDoc.facility.id == facility.id)
#             regulatory_doc = await RegulatoryDoc.find_one(RegulatoryDoc.facility.id == facility.id)

#             result.append({
#                 "id": str(facility.id),
#                 "created_by_id": facility.created_by_id,
#                 "basic": _decrypt_json_field(ce, basic_doc.data) if basic_doc else None,
#                 "address": _decrypt_json_field(ce, address_doc.data) if address_doc else None,
#                 "contacts": _decrypt_json_field(ce, contacts_doc.data) if contacts_doc else None,
#                 "branding": _decrypt_json_field(ce, branding_doc.data) if branding_doc else None,
#                 "structure": _decrypt_json_field(ce, structure_doc.data) if structure_doc else None,
#                 "rooms_beds": _decrypt_json_field(ce, rooms_beds_doc.data) if rooms_beds_doc else None,
#                 "key_contacts": _decrypt_json_field(ce, key_contacts_doc.data) if key_contacts_doc else None,
#                 "partners": _decrypt_json_field(ce, partners_doc.data) if partners_doc else None,
#                 "workstations": _decrypt_json_field(ce, workstations_doc.data) if workstations_doc else None,
#                 "interoperability": _decrypt_json_field(ce, interop_doc.data) if interop_doc else None,
#                 "regulatory": _decrypt_json_field(ce, regulatory_doc.data) if regulatory_doc else None,
#                 "created_at": facility.created_at,
#                 "updated_at": facility.updated_at,
#             })

#         return result
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
    

# @router.post("/facility/{facility_id}/partners")
# async def save_partners(
#     facility_id: str,
#     request: Request,
#     partners: str = Form("[]"),
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         facility = await Facility.get(facility_id)
#         if not facility or facility.created_by_id != str(current_user_id):
#             raise HTTPException(status_code=404, detail="Facility not found")
#         ce = request.app.client_encryption
#         dek = request.app.dek_id
#         partners_list = json.loads(partners or "[]")
#         enc = encrypt_value(ce, dek, json.dumps(partners_list))
#         existing = await PartnersDoc.find_one(PartnersDoc.facility.id == facility.id)
#         if existing:
#             existing.data = enc
#             await existing.save()
#         else:
#             await PartnersDoc(facility=facility, data=enc).insert()
#         return {"id": facility_id}
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.post("/facility/{facility_id}/workstations")
# async def save_workstations(
#     facility_id: str,
#     request: Request,
#     workstations: str = Form("[]"),
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         facility = await Facility.get(facility_id)
#         if not facility or facility.created_by_id != str(current_user_id):
#             raise HTTPException(status_code=404, detail="Facility not found")
#         ce = request.app.client_encryption
#         dek = request.app.dek_id
#         ws_list = json.loads(workstations or "[]")
#         enc = encrypt_value(ce, dek, json.dumps(ws_list))
#         existing = await WorkstationsDoc.find_one(WorkstationsDoc.facility.id == facility.id)
#         if existing:
#             existing.data = enc
#             await existing.save()
#         else:
#             await WorkstationsDoc(facility=facility, data=enc).insert()
#         return {"id": facility_id}
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.post("/facility/{facility_id}/interoperability")
# async def save_interoperability(
#     facility_id: str,
#     request: Request,
#     interoperability: str = Form(None),
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         facility = await Facility.get(facility_id)
#         if not facility or facility.created_by_id != str(current_user_id):
#             raise HTTPException(status_code=404, detail="Facility not found")
#         ce = request.app.client_encryption
#         dek = request.app.dek_id
#         interop_obj = json.loads(interoperability) if interoperability else {}
#         enc = encrypt_value(ce, dek, json.dumps(interop_obj))
#         existing = await InteroperabilityDoc.find_one(InteroperabilityDoc.facility.id == facility.id)
#         if existing:
#             existing.data = enc
#             await existing.save()
#         else:
#             await InteroperabilityDoc(facility=facility, data=enc).insert()
#         return {"id": facility_id}
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.post("/facility/{facility_id}/regulatory")
# async def save_regulatory(
#     facility_id: str,
#     request: Request,
#     regulatory: str = Form(None),
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         facility = await Facility.get(facility_id)
#         if not facility or facility.created_by_id != str(current_user_id):
#             raise HTTPException(status_code=404, detail="Facility not found")
#         ce = request.app.client_encryption
#         dek = request.app.dek_id
#         reg_obj = json.loads(regulatory) if regulatory else {}
#         enc = encrypt_value(ce, dek, json.dumps(reg_obj))
#         existing = await RegulatoryDoc.find_one(RegulatoryDoc.facility.id == facility.id)
#         if existing:
#             existing.data = enc
#             await existing.save()
#         else:
#             await RegulatoryDoc(facility=facility, data=enc).insert()
#         return {"id": facility_id}
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

UPLOAD_DIR_FACILITY_LOGOS = "./uploads/facility_logos"
os.makedirs(UPLOAD_DIR_FACILITY_LOGOS, exist_ok=True)


