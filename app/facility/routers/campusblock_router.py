from datetime import datetime, timezone
from app.accounts.models.user import UserDoc
from app.facility.models.facility import Facility
from fastapi import APIRouter, Request, HTTPException, Depends
from app.facility.models.campusblock import CampusBlock
from app.schemas.facilities.campus_block import CampusBlockSchema
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
import json
from app.auth.deps import get_current_user_id
from app.utils.audit import log_audit

router = APIRouter(prefix="/facility", tags=["Facility"])



def _dec_str(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode() if isinstance(raw, (bytes, bytearray)) else raw


def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return json.loads(decrypted_raw)

def _try_parse_json_dict(val):
    if val is None:
        return None
    if isinstance(val, dict):
        return val
    if not isinstance(val, str):
        return None
    s = val.strip()
    if not s:
        return None
    if s[0] not in ("{", "["):
        return None
    try:
        parsed = json.loads(s)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_block_values(client_encryption, campus_block_doc: CampusBlock):
    code_raw = _dec_str(client_encryption, campus_block_doc.block_code)
    name_raw = _dec_str(client_encryption, campus_block_doc.block_name)

    parsed = _try_parse_json_dict(code_raw) or _try_parse_json_dict(name_raw)
    if parsed:
        code_val = parsed.get("block_code", code_raw)
        name_val = parsed.get("block_name", name_raw)
        return code_val, name_val

    return code_raw, name_raw


@router.post("/create/campusblock/{facility_id}/")
async def create_campus_block(
    facility_id: str,
    campus_block: CampusBlockSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        client_encryption = getattr(request.app, "client_encryption", None)
        if client_encryption is None:
            client_encryption = init_encryption()
            request.app.client_encryption = client_encryption
        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        def enc_or_none(val):
            return encrypt_value(client_encryption, dek_id, val) if val is not None else None

        # ✅ Check Facility
        facilityid = await Facility.get(facility_id)
        if not facilityid:
            raise HTTPException(status_code=404, detail="Facility not found")

        # ✅ Check User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # ✅ Create Campus Block
        campus_block_doc = CampusBlock(
            block_code=enc_or_none(campus_block.block_code),
            block_name=enc_or_none(campus_block.block_name),
            facility_id=facility_id,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await campus_block_doc.insert()

        # ✅ Audit Log (non-blocking safe)
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Facility Campus Block",
                resource_id=str(campus_block_doc.id),
                status="success",
                notes="Facility campus block created successfully",
            )
        except Exception as audit_error:
            print("⚠️ Audit Log Failed:", audit_error)

        return {
            "success": True,
            "facility_id_received": facility_id,
            "campus_block_id": str(campus_block_doc.id),
        }

    except HTTPException:
        # ✅ Re-raise known HTTP errors cleanly
        raise

    except Exception as e:
        # ✅ Catch any unknown crash
        print("❌ Campus Block Create Crash:", str(e))
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating campus block"
        )


@router.get("/get/campusblock/{facility_id}/")
async def get_campus_blocks(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    ce = request.app.client_encryption
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    facility_obj = None
    try:
        from beanie import PydanticObjectId
        facility_obj_id = PydanticObjectId(facility_id)
        facility_obj = await Facility.get(facility_obj_id)
    except Exception:
        pass

    if facility_obj is None:
        facility_obj = await Facility.get(facility_id)
    if not facility_obj:
        raise HTTPException(status_code=404, detail="Facility not found")

   
    # campus_blocks = await CampusBlock.find({"facility_id.$id": facility_obj.id}).to_list()
    campus_blocks = await CampusBlock.find(
    CampusBlock.facility_id.id == facility_obj.id,
    CampusBlock.created_by.id == user.id
    ).to_list()

    
    docs = []
    for d in campus_blocks:
        block_code, block_name = _extract_block_values(ce, d)
        docs.append({
            'id': str(d.id),
            'block_code': block_code,
            'block_name': block_name,
            "created_at": d.created_at,
            "updated_at": d.updated_at,
        })
       
    
    

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Facility Campus Block",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Campus blocks fetched successfully",
        )
    except Exception:
        pass

    return docs


@router.put("/update/campusblock/{campus_block_id}/")
async def update_campus_block(
    campus_block_id: str,
    campus_block: CampusBlockSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    client_encryption = getattr(request.app, "client_encryption", None)
    if client_encryption is None:
        client_encryption = init_encryption()
        request.app.client_encryption = client_encryption
    dek_id = getattr(request.app, "dek_id", None)
    if dek_id is None:
        dek_id = ensure_data_key()
        request.app.dek_id = dek_id

    def enc_or_none(val):
        return encrypt_value(client_encryption, dek_id, val) if val is not None else None

    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        from beanie import PydanticObjectId
        cb_obj_id = PydanticObjectId(campus_block_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Campus Block ID format")

    cb = await CampusBlock.get(cb_obj_id)
    if not cb:
        raise HTTPException(status_code=404, detail="Campus block not found")

    update_data = campus_block.model_dump(exclude_unset=True, exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    current_code, current_name = _extract_block_values(client_encryption, cb)
    new_code = update_data.get("block_code", current_code)
    new_name = update_data.get("block_name", current_name)

    cb.block_code = enc_or_none(new_code)
    cb.block_name = enc_or_none(new_name)
    cb.updated_at = datetime.now(timezone.utc)
    await cb.save()

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Update",
            resource="Facility Campus Block",
            resource_id=str(cb.id),
            status="success",
            notes="Facility campus block updated successfully",
        )
    except Exception:
        pass

    return {
        "success": True,
        "campus_block_id": str(cb.id),
        "updated": {
            "block_code": new_code,
            "block_name": new_name,
        },
        "updated_at": cb.updated_at,
    }
