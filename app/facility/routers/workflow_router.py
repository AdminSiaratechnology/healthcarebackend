from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.workflow import FacilityWorkflowSchema
from beanie import PydanticObjectId
import json
import os
from app.facility.models.workflow import WorkflowDoc

router = APIRouter(prefix="/facility", tags=["Facility"])


@router.post("/create/workflow/{facility_id}/")
async def create_workflow(
    facility_id: str,
    wf: FacilityWorkflowSchema,
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

        def enc_json_or_none(obj):
            return (
                encrypt_value(
                    client_encryption,
                    dek_id,
                    json.dumps(obj.model_dump(mode="json"))
                ) if obj is not None else None
            )

        def enc_list(objs):
            return encrypt_value(
                client_encryption,
                dek_id,
                json.dumps([o.model_dump(mode="json") for o in objs])
            ) if objs is not None else None

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

        doc = WorkflowDoc(
            facility_id=facility,
            admission_workflow=enc_json_or_none(wf.adt_workflow),
            documentation_workflow=enc_json_or_none(wf.documentation_workflow),
            billing_workflow=enc_json_or_none(wf.billing_workflow),
            clinical_protocols=enc_json_or_none(wf.clinical_protocols),
            vaccine_rules=enc_json_or_none(wf.vaccine_rules),
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
                resource="Workflow",
                resource_id=str(doc.id),
                status="success",
                notes="Facility workflow created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "workflow_id": str(doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Create",
                resource="Workflow",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while creating workflow")


def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return json.loads(decrypted_raw)


@router.get("/get/workflow/{facility_id}/")
async def get_workflows(
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

    
     # ---------------- ENCRYPTION ----------------
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    # ---------------- Work Flows  ----------------
    work_flow = await WorkflowDoc.find(
        WorkflowDoc.facility_id.id == facility_obj.id,
        WorkflowDoc.created_by.id == user.id
    ).sort("-created_at").to_list()


    # ---------------- RESPONSE ----------------


    result = [
        {
            "id": str(wf.id),
            "admission_workflow": _decrypt_json_field(ce, wf.admission_workflow),
            "documentation_workflow": _decrypt_json_field(ce, wf.documentation_workflow),
            "billing_workflow": _decrypt_json_field(ce, wf.billing_workflow),
            "clinical_protocols": _decrypt_json_field(ce, wf.clinical_protocols),
            "vaccine_rules": _decrypt_json_field(ce, wf.vaccine_rules),
            "created_at": wf.created_at,
            "updated_at": wf.updated_at,
        } for wf in work_flow
    ]

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Workflow",
            resource_id=str(facility_obj.id),
            status="success",
            notes="Workflows fetched successfully",
        )
    except Exception:
        pass

    return result
