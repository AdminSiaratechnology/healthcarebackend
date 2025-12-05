from datetime import datetime, timezone
from app.accounts.models.user import UserDoc
from app.facility.models.facility import Facility
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import ValidationError
from app.facility.models.campusblock import CampusBlock
from app.schemas.facilities.campus_block import CampusBlockSchema
from app.encryption.encryption import encrypt_value, decrypt_value
import json
from app.auth.deps import get_current_user_id
from app.utils.audit import log_audit

router = APIRouter(prefix="/facility", tags=["Facility"])



def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return json.loads(decrypted_raw)


@router.post("/create/campusblock/{facility_id}/")
async def create_campus_block(
    facility_id: str,
    campus_block: CampusBlockSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        client_encryption = request.app.client_encryption
        dek_id = request.app.dek_id

        # ✅ Encrypt Body
        try:
            body = json.dumps(campus_block.model_dump())
            enc_struct = encrypt_value(client_encryption, dek_id, body)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Encryption failed: {str(e)}"
            )

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
            block_code=enc_struct,
            block_name=enc_struct,
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
