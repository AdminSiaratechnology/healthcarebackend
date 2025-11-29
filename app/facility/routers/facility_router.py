from typing import Annotated

from fastapi import APIRouter, Request, HTTPException, Depends, Form
from pydantic import ValidationError
# from app.schemas.facility import FacilityPayload
from app.schemas.facility import Branding,Address,Regulatory
from app.facility.models.facility import Facility
from app.facility.models.basic import BasicDoc
from app.facility.models.address import AddressDoc
from app.facility.models.contacts import ContactsDoc
from app.facility.models.branding import BrandingDoc
from app.facility.models.structure import StructureDoc
from app.facility.models.rooms_beds import RoomsBedsDoc
from app.facility.models.key_contacts import KeyContactsDoc
from app.facility.models.partners import PartnersDoc
from app.facility.models.it_workstations import WorkstationsDoc
from app.facility.models.interoperability import InteroperabilityDoc
from app.facility.models.regulatory import RegulatoryDoc
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value
import json



router = APIRouter(prefix="/facility", tags=["Facility"])


# def _facility_payload_from_form(
#     basic: Annotated[str, Form()],
#     branding: Annotated[str | None, Form()] = None,
#     structure: Annotated[str | None, Form()] = None,
# ) -> FacilityPayload:
#     try:
#         payload_content = {"basic": json.loads(basic)}
#         if branding:
#             payload_content["branding"] = json.loads(branding)
#         if structure:
#             payload_content["structure"] = json.loads(structure)
#     except json.JSONDecodeError as exc:
#         raise HTTPException(
#             status_code=422, detail=f"Invalid JSON provided for facility payload: {exc.msg}"
#         ) from exc

#     try:
#         return FacilityPayload.model_validate(payload_content)
#     except ValidationError as exc:
#         raise HTTPException(status_code=422, detail=exc.errors())


def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return json.loads(decrypted_raw)


# @router.post("/facility")
# async def create_facility_basic(
#     request: Request,
#     payload: FacilityPayload = Depends(_facility_payload_from_form),
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         client_encryption = request.app.client_encryption
#         dek_id = request.app.dek_id
#         basic_enc = encrypt_value(client_encryption, dek_id, payload.basic.model_dump_json())
#         branding_enc = None
#         if payload.branding:
#             branding_enc = encrypt_value(client_encryption, dek_id, payload.branding.model_dump_json())
#         structure_enc = None
#         if payload.structure:
#             structure_enc = encrypt_value(client_encryption, dek_id, payload.structure.model_dump_json())
#         creator = await UserDoc.get(current_user_id)
#         if not creator:
#             raise HTTPException(status_code=404, detail="Creator user not found")
#         facility = Facility(
#             basic=basic_enc,
#             branding=branding_enc,
#             structure=structure_enc,
#             created_by=creator,
#             created_by_id=str(creator.id),
#         )
#         await facility.insert()
#         return {"id": str(facility.id)}
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
from typing import Optional
from fastapi import UploadFile, Form, HTTPException, File
import os
import uuid
import json
UPLOAD_DIR = "./uploads/logos"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post('/facility')
async def create_facility(
    request: Request,
    facility_name: str = Form(...),
    facility_type: str = Form(...),
    main_phone: str = Form(...),
    facility_code: Optional[str] = Form(None),
    fax: Optional[str] = Form(None),
    general_email: Optional[str] = Form(None),
    website_url: Optional[str] = Form(None),
    timezone: Optional[str] = Form(None),
    operatinghour : Optional[str] = Form(None),
    
    address: str = Form(...),

    logo: Optional[UploadFile] = File(None),
    primary_color: Optional[str] = Form("#0066cc"),
    secondary_color: Optional[str] = Form(None),
    accent_color: Optional[str] = Form(None),
    brand_notes: Optional[str] = Form(None),

    campus_block: Optional[str] = Form("[]"),
    floors: Optional[str] = Form("[]"),
    beds: Optional[str] = Form("[]"),
    key_contacts: Optional[str] = Form("[]"),
    partners: Optional[str] = Form("[]"),
    workstations: Optional[str] = Form("[]"),
    interoperability: Optional[str] = Form(None),
    regulatory: Optional[str] = Form(None),
    current_user_id: str = Depends(get_current_user_id),
):
    # Duplicate check (optional: implement facility_code unique check if needed)

    # Parse JSON fields (form inputs)
    try:
        addr = json.loads(address) if address else None
        wings_list = json.loads(campus_block or "[]")
        rooms_list = json.loads(floors or "[]")
        beds_list = json.loads(beds or "[]")
        contacts_list = json.loads(key_contacts or "[]")
        partners_list = json.loads(partners or "[]")
        workstations_list = json.loads(workstations or "[]")
        interop = json.loads(interoperability) if interoperability else None
        reg = json.loads(regulatory) if regulatory else None
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    # Required checks
    if not facility_name or not facility_type or not main_phone or not addr:
        raise HTTPException(status_code=422, detail="facility_name, facility_type, main_phone, address are required")

    # Logo Upload
    logo_url = None
    if logo and logo.filename:
        ext = logo.filename.split(".")[-1].lower()
        if ext not in ["png", "jpg", "jpeg", "gif", "webp", "svg"]:
            raise HTTPException(400, "Invalid image format")
        filename = f"{uuid.uuid4()}.{ext}"
        path = os.path.join(UPLOAD_DIR, filename)
        with open(path, "wb") as f:
            f.write(await logo.read())
        logo_url = f"http://localhost:8000/uploads/logos/{filename}"  # Change domain in production
    try:
        client_encryption = request.app.client_encryption
        dek_id = request.app.dek_id

        creator = await UserDoc.get(current_user_id)
        if not creator:
            raise HTTPException(status_code=404, detail="Creator user not found")

        basic_payload = {
            "facility_name": facility_name,
            "facility_type": facility_type,
            "facility_code": facility_code,
        }
        contacts_payload = {
            "main_phone": main_phone,
            "fax": fax,
            "general_email": general_email,
            "website_url": website_url,
            "timezone": timezone,
            "operating_hour": operatinghour,
        }
        branding_payload = None
        if logo_url or primary_color or secondary_color or accent_color or brand_notes:
            branding_payload = {
                "logo_url": logo_url,
                "primary_color": primary_color,
                "secondary_color": secondary_color,
                "accent_color": accent_color,
                "brand_notes": brand_notes,
            }
        structure_payload = { "campus_blocks": wings_list }
        rooms_beds_payload = { "rooms": rooms_list, "beds": beds_list }

        facility = Facility(
            created_by=creator,
            created_by_id=str(creator.id),
        )
        await facility.insert()

        basic_enc = encrypt_value(client_encryption, dek_id, json.dumps(basic_payload))
        await BasicDoc(facility=facility, data=basic_enc).insert()

        address_enc = encrypt_value(client_encryption, dek_id, json.dumps(addr))
        await AddressDoc(facility=facility, data=address_enc).insert()

        contacts_enc = encrypt_value(client_encryption, dek_id, json.dumps(contacts_payload))
        await ContactsDoc(facility=facility, data=contacts_enc).insert()

        if branding_payload:
            branding_enc = encrypt_value(client_encryption, dek_id, json.dumps(branding_payload))
            await BrandingDoc(facility=facility, data=branding_enc).insert()

        structure_enc = encrypt_value(client_encryption, dek_id, json.dumps(structure_payload))
        await StructureDoc(facility=facility, data=structure_enc).insert()

        rooms_beds_enc = encrypt_value(client_encryption, dek_id, json.dumps(rooms_beds_payload))
        await RoomsBedsDoc(facility=facility, data=rooms_beds_enc).insert()

        if contacts_list:
            contacts_list_enc = encrypt_value(client_encryption, dek_id, json.dumps(contacts_list))
            await KeyContactsDoc(facility=facility, data=contacts_list_enc).insert()
        if partners_list:
            partners_enc = encrypt_value(client_encryption, dek_id, json.dumps(partners_list))
            await PartnersDoc(facility=facility, data=partners_enc).insert()
        if workstations_list:
            workstations_enc = encrypt_value(client_encryption, dek_id, json.dumps(workstations_list))
            await WorkstationsDoc(facility=facility, data=workstations_enc).insert()
        if interop is not None:
            interop_enc = encrypt_value(client_encryption, dek_id, json.dumps(interop))
            await InteroperabilityDoc(facility=facility, data=interop_enc).insert()
        if reg is not None:
            regulatory_enc = encrypt_value(client_encryption, dek_id, json.dumps(reg))
            await RegulatoryDoc(facility=facility, data=regulatory_enc).insert()

        return {"message": "Facility created!", "id": str(facility.id)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/facility")
async def get_facility_for_creator(request: Request, current_user_id: str = Depends(get_current_user_id)):
    try:
        facilities = await Facility.find(Facility.created_by_id == str(current_user_id)).to_list()
        if not facilities:
            raise HTTPException(status_code=404, detail="Facility not found")

        result = []
        for facility in facilities:
            ce = request.app.client_encryption
            basic_doc = await BasicDoc.find_one(BasicDoc.facility.id == facility.id)
            address_doc = await AddressDoc.find_one(AddressDoc.facility.id == facility.id)
            contacts_doc = await ContactsDoc.find_one(ContactsDoc.facility.id == facility.id)
            branding_doc = await BrandingDoc.find_one(BrandingDoc.facility.id == facility.id)
            structure_doc = await StructureDoc.find_one(StructureDoc.facility.id == facility.id)
            rooms_beds_doc = await RoomsBedsDoc.find_one(RoomsBedsDoc.facility.id == facility.id)
            key_contacts_doc = await KeyContactsDoc.find_one(KeyContactsDoc.facility.id == facility.id)
            partners_doc = await PartnersDoc.find_one(PartnersDoc.facility.id == facility.id)
            workstations_doc = await WorkstationsDoc.find_one(WorkstationsDoc.facility.id == facility.id)
            interop_doc = await InteroperabilityDoc.find_one(InteroperabilityDoc.facility.id == facility.id)
            regulatory_doc = await RegulatoryDoc.find_one(RegulatoryDoc.facility.id == facility.id)

            result.append({
                "id": str(facility.id),
                "created_by_id": facility.created_by_id,
                "basic": _decrypt_json_field(ce, basic_doc.data) if basic_doc else None,
                "address": _decrypt_json_field(ce, address_doc.data) if address_doc else None,
                "contacts": _decrypt_json_field(ce, contacts_doc.data) if contacts_doc else None,
                "branding": _decrypt_json_field(ce, branding_doc.data) if branding_doc else None,
                "structure": _decrypt_json_field(ce, structure_doc.data) if structure_doc else None,
                "rooms_beds": _decrypt_json_field(ce, rooms_beds_doc.data) if rooms_beds_doc else None,
                "key_contacts": _decrypt_json_field(ce, key_contacts_doc.data) if key_contacts_doc else None,
                "partners": _decrypt_json_field(ce, partners_doc.data) if partners_doc else None,
                "workstations": _decrypt_json_field(ce, workstations_doc.data) if workstations_doc else None,
                "interoperability": _decrypt_json_field(ce, interop_doc.data) if interop_doc else None,
                "regulatory": _decrypt_json_field(ce, regulatory_doc.data) if regulatory_doc else None,
                "created_at": facility.created_at,
                "updated_at": facility.updated_at,
            })

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.post("/facility/{facility_id}/partners")
async def save_partners(
    facility_id: str,
    request: Request,
    partners: str = Form("[]"),
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        facility = await Facility.get(facility_id)
        if not facility or facility.created_by_id != str(current_user_id):
            raise HTTPException(status_code=404, detail="Facility not found")
        ce = request.app.client_encryption
        dek = request.app.dek_id
        partners_list = json.loads(partners or "[]")
        enc = encrypt_value(ce, dek, json.dumps(partners_list))
        existing = await PartnersDoc.find_one(PartnersDoc.facility.id == facility.id)
        if existing:
            existing.data = enc
            await existing.save()
        else:
            await PartnersDoc(facility=facility, data=enc).insert()
        return {"id": facility_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/facility/{facility_id}/workstations")
async def save_workstations(
    facility_id: str,
    request: Request,
    workstations: str = Form("[]"),
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        facility = await Facility.get(facility_id)
        if not facility or facility.created_by_id != str(current_user_id):
            raise HTTPException(status_code=404, detail="Facility not found")
        ce = request.app.client_encryption
        dek = request.app.dek_id
        ws_list = json.loads(workstations or "[]")
        enc = encrypt_value(ce, dek, json.dumps(ws_list))
        existing = await WorkstationsDoc.find_one(WorkstationsDoc.facility.id == facility.id)
        if existing:
            existing.data = enc
            await existing.save()
        else:
            await WorkstationsDoc(facility=facility, data=enc).insert()
        return {"id": facility_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/facility/{facility_id}/interoperability")
async def save_interoperability(
    facility_id: str,
    request: Request,
    interoperability: str = Form(None),
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        facility = await Facility.get(facility_id)
        if not facility or facility.created_by_id != str(current_user_id):
            raise HTTPException(status_code=404, detail="Facility not found")
        ce = request.app.client_encryption
        dek = request.app.dek_id
        interop_obj = json.loads(interoperability) if interoperability else {}
        enc = encrypt_value(ce, dek, json.dumps(interop_obj))
        existing = await InteroperabilityDoc.find_one(InteroperabilityDoc.facility.id == facility.id)
        if existing:
            existing.data = enc
            await existing.save()
        else:
            await InteroperabilityDoc(facility=facility, data=enc).insert()
        return {"id": facility_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/facility/{facility_id}/regulatory")
async def save_regulatory(
    facility_id: str,
    request: Request,
    regulatory: str = Form(None),
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        facility = await Facility.get(facility_id)
        if not facility or facility.created_by_id != str(current_user_id):
            raise HTTPException(status_code=404, detail="Facility not found")
        ce = request.app.client_encryption
        dek = request.app.dek_id
        reg_obj = json.loads(regulatory) if regulatory else {}
        enc = encrypt_value(ce, dek, json.dumps(reg_obj))
        existing = await RegulatoryDoc.find_one(RegulatoryDoc.facility.id == facility.id)
        if existing:
            existing.data = enc
            await existing.save()
        else:
            await RegulatoryDoc(facility=facility, data=enc).insert()
        return {"id": facility_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
