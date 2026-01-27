from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.workflow import FacilityWorkflowSchema
from beanie import PydanticObjectId
from beanie.operators import In
import json
import os
from datetime import date
from bson import ObjectId
from app.facility.models.workflow import WorkflowDoc
import re
from typing import Optional
router = APIRouter(prefix="/workflow", tags=["Work-Flows"])


# @router.post("/create/workflow/{facility_id}/")
# async def create_workflow(
#     facility_id: str,
#     wf: FacilityWorkflowSchema,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id)
# ):
#     try:
#         client_encryption = getattr(request.app, "client_encryption", None)
#         if client_encryption is None:
#             client_encryption = init_encryption()
#         dek_id = getattr(request.app, "dek_id", None)
#         if dek_id is None:
#             dek_id = ensure_data_key()

#         def enc_json_or_none(obj):
#             return (
#                 encrypt_value(
#                     client_encryption,
#                     dek_id,
#                     json.dumps(obj.model_dump(mode="json"))
#                 ) if obj is not None else None
#             )

#         def enc_list(objs):
#             return encrypt_value(
#                 client_encryption,
#                 dek_id,
#                 json.dumps([o.model_dump(mode="json") for o in objs])
#             ) if objs is not None else None

#         try:
#             facility_obj_id = PydanticObjectId(facility_id)
#         except Exception:
#             raise HTTPException(status_code=400, detail="Invalid Facility ID format")

#         facility = await Facility.get(facility_obj_id)
#         if not facility:
#             raise HTTPException(status_code=404, detail="Facility not found")

#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         doc = WorkflowDoc(
#             facility_id=facility,
#             admission_workflow=enc_json_or_none(wf.adt_workflow),
#             documentation_workflow=enc_json_or_none(wf.documentation_workflow),
#             billing_workflow=enc_json_or_none(wf.billing_workflow),
#             clinical_protocols=enc_json_or_none(wf.clinical_protocols),
#             vaccine_rules=enc_json_or_none(wf.vaccine_rules),
#             created_by=user,
#             created_at=datetime.now(timezone.utc),
#             updated_at=datetime.now(timezone.utc),
#         )

#         await doc.insert()

#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Create",
#                 resource="Workflow",
#                 resource_id=str(doc.id),
#                 status="success",
#                 notes="Facility workflow created successfully",
#             )
#         except Exception:
#             pass

#         return {
#             "success": True,
#             "facility_id_received": str(facility.id),
#             "workflow_id": str(doc.id),
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(current_user_id),
#                 action="Create",
#                 resource="Workflow",
#                 resource_id="N/A",
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail="Internal Server Error while creating workflow")



@router.post("/create/{facility_id}/")
async def create_facility_workflow(
    facility_id: str,
    payload: FacilityWorkflowSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # 1️⃣ User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 2️⃣ Encryption init  
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        # 3️⃣ Facility ownership check
        facility = await Facility.find_one(
            Facility.id == ObjectId(facility_id),
            Facility.created_by.id == user.id,
            # Facility.is_deleted == False,
        )
        if not facility:
            raise HTTPException(
                status_code=404,
                detail="Facility not found or you don't have permission"
            )

        # 4️⃣ Check if workflow already exists for this facility (ONE-TO-ONE)
        existing = await WorkflowDoc.find_one(
            WorkflowDoc.facility_id.id == facility.id,
            WorkflowDoc.is_deleted == False
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Workflow configuration already exists for this facility. Only one allowed per facility."
            )

        # 5️⃣ Custom serializer for date/datetime (future-proof)
        def date_serializer(obj):
            if isinstance(obj, date):
                return obj.isoformat()
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")

        # 6️⃣ Encrypt each workflow section separately
        adt_enc = None
        if payload.adt_workflow:
            adt_json = json.dumps(payload.adt_workflow.model_dump(), default=date_serializer)
            adt_enc = encrypt_value(ce, dek_id, adt_json)

        documentation_enc = None
        if payload.documentation_workflow:
            doc_json = json.dumps(payload.documentation_workflow.model_dump(), default=date_serializer)
            documentation_enc = encrypt_value(ce, dek_id, doc_json)

        billing_enc = None
        if payload.billing_workflow:
            billing_json = json.dumps(payload.billing_workflow.model_dump(), default=date_serializer)
            billing_enc = encrypt_value(ce, dek_id, billing_json)

        clinical_enc = None
        if payload.clinical_protocols:
            clinical_json = json.dumps(payload.clinical_protocols.model_dump(), default=date_serializer)
            clinical_enc = encrypt_value(ce, dek_id, clinical_json)

        vaccine_enc = None
        if payload.vaccine_rules:
            vaccine_json = json.dumps(payload.vaccine_rules.model_dump(), default=date_serializer)
            vaccine_enc = encrypt_value(ce, dek_id, vaccine_json)

        # 7️⃣ Save
        workflow_doc = WorkflowDoc(
            facility_id=facility,
            created_by=user,
            
            admission_workflow=adt_enc,
            documentation_workflow=documentation_enc,
            billing_workflow=billing_enc,
            clinical_protocols=clinical_enc,
            vaccine_rules=vaccine_enc,
            
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await workflow_doc.insert()

        # 8️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Facility Workflow",
                resource_id=str(workflow_doc.id),
                status="success",
                notes="Facility workflow configuration created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "workflow_id": str(workflow_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility workflow"
        )



@router.get("/list/")
async def get_facility_workflows(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by facility name"),
):
    try:
        # 1️⃣ User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
       
        # 2️⃣ Encryption
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        # ----------------------------
        # 3️⃣ Pagination calculation
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 4️⃣ Query conditions + search handling
        # ----------------------------
        conditions = [
            WorkflowDoc.created_by.id == user.id,
            WorkflowDoc.is_deleted == False
        ]

        if status:
            conditions.append(WorkflowDoc.status == status.lower())

        workflows_list = []
        total = 0

        if search:
            search_value = search.lower()

            matching_facilities = await Facility.find(
                Facility.facility_name_search == re.compile(
                    f".*{search_value}.*", re.IGNORECASE
                ),
                Facility.created_by.id == user.id
            ).to_list()

            if matching_facilities:
                facility_ids = [f.id for f in matching_facilities]

                conditions.append(
                    In(WorkflowDoc.facility_id.id, facility_ids)
                )

                workflows_list = await (
                    WorkflowDoc.find(*conditions, fetch_links=True)
                    .sort("-created_at")
                    .skip(skip)
                    .limit(page_size)
                    .to_list()
                )
                total = await WorkflowDoc.find(*conditions).count()
            # else: workflows_list aur total 0 hi rahenge (empty result)
        else:
            # No search → normal query
            workflows_list = await (
                WorkflowDoc.find(*conditions, fetch_links=True)
                .sort("-created_at")
                .skip(skip)
                .limit(page_size)
                .to_list()
            )
            total = await WorkflowDoc.find(*conditions).count()

        # ----------------------------
        # 5️⃣ Response (decrypt each JSON section)
        # ----------------------------

        result = []
        for wf in workflows_list:
            # Decrypt each section
            adt_dec = None
            if wf.admission_workflow:
                try:
                    adt_json = decrypt_value(ce, wf.admission_workflow)
                    adt_dec = json.loads(adt_json)
                except:
                    adt_dec = None

            doc_dec = None
            if wf.documentation_workflow:
                try:
                    doc_json = decrypt_value(ce, wf.documentation_workflow)
                    doc_dec = json.loads(doc_json)
                except:
                    doc_dec = None

            billing_dec = None
            if wf.billing_workflow:
                try:
                    billing_json = decrypt_value(ce, wf.billing_workflow)
                    billing_dec = json.loads(billing_json)
                except:
                    billing_dec = None

            clinical_dec = None
            if wf.clinical_protocols:
                try:
                    clinical_json = decrypt_value(ce, wf.clinical_protocols)
                    clinical_dec = json.loads(clinical_json)
                except:
                    clinical_dec = None

            vaccine_dec = None
            if wf.vaccine_rules:
                try:
                    vaccine_json = decrypt_value(ce, wf.vaccine_rules)
                    vaccine_dec = json.loads(vaccine_json)
                except:
                    vaccine_dec = None

            result.append({
                "id": str(wf.id),
                "facility_id": str(wf.facility_id.id) if wf.facility_id else None,
                "facility_name": (
                    wf.facility_id.facility_name_search
                    if wf.facility_id else None
                ),
                "adt_workflow": adt_dec,
                "documentation_workflow": doc_dec,
                "billing_workflow": billing_dec,
                "clinical_protocols": clinical_dec,
                "vaccine_rules": vaccine_dec,
                "status": wf.status,
                "created_at": wf.created_at,
                "updated_at": wf.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Facility Workflow",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Workflows fetched | "
                    f"page={page}, page_size={page_size}, "
                    f"status={status}, search={search}, returned={len(result)}"
                ),
            )
        except Exception:
            pass

        return {
            "success": True,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "count": len(result),
            "total": total,
            "data": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")



@router.put("/update/{workflow_id}/")
async def update_facility_workflow(
    workflow_id: str,
    payload: FacilityWorkflowSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # 1️⃣ User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 2️⃣ Encryption init
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        # 3️⃣ Get Workflow config
        try:
            wf_obj_id = ObjectId(workflow_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Workflow ID")

        wf = await WorkflowDoc.find_one(
            WorkflowDoc.id == wf_obj_id,
            WorkflowDoc.created_by.id == user.id,
            WorkflowDoc.is_deleted == False,
            fetch_links=True
        )

        if not wf:
            raise HTTPException(status_code=404, detail="Workflow configuration not found")

        # 4️⃣ Custom serializer (future-proof)
        def date_serializer(obj):
            if isinstance(obj, date):
                return obj.isoformat()
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")

        # 5️⃣ Partial update - encrypt only provided sections
        if payload.adt_workflow is not None:
            adt_json = json.dumps(payload.adt_workflow.model_dump(), default=date_serializer)
            wf.admission_workflow = encrypt_value(ce, dek_id, adt_json)

        if payload.documentation_workflow is not None:
            doc_json = json.dumps(payload.documentation_workflow.model_dump(), default=date_serializer)
            wf.documentation_workflow = encrypt_value(ce, dek_id, doc_json)

        if payload.billing_workflow is not None:
            billing_json = json.dumps(payload.billing_workflow.model_dump(), default=date_serializer)
            wf.billing_workflow = encrypt_value(ce, dek_id, billing_json)

        if payload.clinical_protocols is not None:
            clinical_json = json.dumps(payload.clinical_protocols.model_dump(), default=date_serializer)
            wf.clinical_protocols = encrypt_value(ce, dek_id, clinical_json)

        if payload.vaccine_rules is not None:
            vaccine_json = json.dumps(payload.vaccine_rules.model_dump(), default=date_serializer)
            wf.vaccine_rules = encrypt_value(ce, dek_id, vaccine_json)

        # 6️⃣ Timestamp
        wf.updated_at = datetime.now(timezone.utc)

        await wf.save()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Facility Workflow",
                resource_id=str(wf.id),
                status="success",
                notes="Facility workflow configuration updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "workflow_id": str(wf.id),
            "message": "Facility workflow updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating facility workflow"
        )