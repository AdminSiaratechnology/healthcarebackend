from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value,init_encryption,ensure_data_key,encrypt_value_deterministic,encrypt_dict,decrypt_value
from app.utils.audit import log_audit
from app.schemas.facilities.statereportingidentifiers import StateReportingIdentifiersSchema
from beanie import PydanticObjectId
import json
import os
from app.facility.models.state_reporting_identifiers import StateReportingIdentifiersDocs
from bson import ObjectId
from typing import Optional
import re
router = APIRouter(prefix="/state-reporting", tags=["State Reporting Identifiers"])



@router.post("/create/state-reporting-identifiers/{facility_id}/")
async def create_state_reporting_identifier(
    facility_id: str,
    payload: StateReportingIdentifiersSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        # 1️⃣ User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 2️⃣ Encryption init (consistent with all previous APIs)
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        # 3️⃣ Validate Facility ID format
        try:
            facility_obj_id = ObjectId(facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")

        # 4️⃣ Facility ownership + existence check
        facility = await Facility.find_one(
            Facility.id == facility_obj_id,
            Facility.created_by.id == user.id,
            # Facility.is_deleted == False,
        )
        if not facility:
            raise HTTPException(
                status_code=404,
                detail="Facility not found or you don't have permission to add identifiers"
            )

        # 5️⃣ Normalize for duplicate check & search
        if not payload.registry_system_name:
            raise HTTPException(status_code=400, detail="Registry system name is required")

        normalized_name = payload.registry_system_name.strip().lower()

        # 6️⃣ Duplicate check (same facility + same registry_system_name)
        existing = await StateReportingIdentifiersDocs.find_one(
            StateReportingIdentifiersDocs.facility_id.id == facility.id,
            StateReportingIdentifiersDocs.registry_system_name_search == normalized_name,
            StateReportingIdentifiersDocs.is_deleted == False
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="State reporting identifier with this registry system name already exists for this facility"
            )

        # 7️⃣ Encrypt fields
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "registry_system_name": payload.registry_system_name,
                "identifier_value": payload.identifier_value,
            }
        )

        # 8️⃣ Create document
        doc = StateReportingIdentifiersDocs(
            facility_id=facility,
            created_by=user,
            
            registry_system_name=encrypted["registry_system_name"],
            identifier_value=encrypted["identifier_value"],
            
            registry_system_name_search=normalized_name,
            
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await doc.insert()

        # 9️⃣ Audit log
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="StateReportingIdentifiers",
                resource_id=str(doc.id),
                status="success",
                notes=f"State reporting identifier created: {payload.registry_system_name}",
            )
        except Exception:
            pass  # non-blocking

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "state_reporting_identifier_id": str(doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
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



# @router.get("/get/state-reporting-identifiers/{facility_id}/")
# async def get_state_reporting_identifiers(
#     facility_id: str,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id)
# ):
#     user = await UserDoc.get(current_user_id)
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     facility_obj = None
#     try:
#         facility_obj_id = PydanticObjectId(facility_id)
#         facility_obj = await Facility.get(facility_obj_id)
#     except Exception:
#         pass

#     if facility_obj is None:
#         facility_obj = await Facility.get(facility_id)
#     if not facility_obj:
#         raise HTTPException(status_code=404, detail="Facility not found")

#      # ---------------- ENCRYPTION ----------------
#     ce = getattr(request.app, "client_encryption", None)
#     if ce is None:
#         ce = init_encryption()
#         request.app.client_encryption = ce

#      # ---------------- State Reporting  ----------------
#     state_reporting = await StateReportingIdentifiersDocs.find(
#         StateReportingIdentifiersDocs.facility_id.id == facility_obj.id,
#         StateReportingIdentifiersDocs.created_by.id == user.id
#     ).sort("-created_at").to_list()


#     # ---------------- RESPONSE ----------------


#     result = [
#         {
#             "id": str(item.id),
#             "registry_system_name": _decrypt_json_field(ce, item.registry_system_name),
#             "identifier_value": _decrypt_json_field(ce, item.identifier_value),
#             "created_at": item.created_at,
#             "updated_at": item.updated_at,
#         } for item in state_reporting
#     ]

#     try:
#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Read",
#             resource="StateReportingIdentifiers",
#             resource_id=str(facility_obj.id),
#             status="success",
#             notes="State reporting identifiers fetched successfully",
#         )
#     except Exception:
#         pass

#     return result



@router.get("/list/")
async def get_facility_state_reporting_identifiers(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    search: Optional[str] = Query(None, description="Search by registry system name"),
    status: Optional[str] = Query(None),
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
        # 3️⃣ Query conditions (Beanie style)
        # ----------------------------
        conditions = [
            StateReportingIdentifiersDocs.created_by.id == user.id,
            StateReportingIdentifiersDocs.is_deleted == False
        ]

        if status:
            conditions.append(StateReportingIdentifiersDocs.status == status.lower())

        if search:
            search_value = search.lower()
            conditions.append(
                StateReportingIdentifiersDocs.registry_system_name_search == re.compile(f".*{search_value}.*", re.IGNORECASE)
            )

        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------

        identifiers = await (
            StateReportingIdentifiersDocs.find(
                *conditions,
                fetch_links=True
            )
            .sort("-created_at")
            .skip(skip)
            .limit(page_size)
            .to_list()
        )

        # ----------------------------
        # 6️⃣ Total count (IMPORTANT)
        # ----------------------------
        total = await StateReportingIdentifiersDocs.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response (decrypt fields)
        # ----------------------------

        result = []
        for identifier in identifiers:
            result.append({
                "id": str(identifier.id),
                "facility_id": str(identifier.facility_id.id) if identifier.facility_id else None,
                "registry_system_name": decrypt_value(ce, identifier.registry_system_name),
                "identifier_value": decrypt_value(ce, identifier.identifier_value),
                
                "status": identifier.status,
                "created_at": identifier.created_at,
                "updated_at": identifier.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="StateReportingIdentifiers",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility State Reporting Identifiers fetched | "
                    f"page={page}, page_size={page_size}, "
                    f"search={search}, status={status}, "
                    f"returned={len(result)}"
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


@router.put("/update/{state_reporting_identifier_id}/")
async def update_state_reporting_identifier(
    state_reporting_identifier_id: str,
    payload: StateReportingIdentifiersSchema,
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

        # 3️⃣ Get State Reporting Identifier
        try:
            identifier_obj_id = ObjectId(state_reporting_identifier_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid State Reporting Identifier ID")

        identifier = await StateReportingIdentifiersDocs.find_one(
            StateReportingIdentifiersDocs.id == identifier_obj_id,
            StateReportingIdentifiersDocs.created_by.id == user.id,
            StateReportingIdentifiersDocs.is_deleted == False,
            fetch_links=True
        )

        if not identifier:
            raise HTTPException(status_code=404, detail="State reporting identifier not found")

        # 4️⃣ Normalize & duplicate check if registry_system_name is changing
        if payload.registry_system_name is not None:
            normalized_new_name = payload.registry_system_name.strip().lower()

            duplicate = await StateReportingIdentifiersDocs.find_one(
                StateReportingIdentifiersDocs.facility_id.id == identifier.facility_id.id,
                StateReportingIdentifiersDocs.registry_system_name_search == normalized_new_name,
                StateReportingIdentifiersDocs.id != identifier.id,
                StateReportingIdentifiersDocs.is_deleted == False,
            )
            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="Another state reporting identifier with this registry system name already exists in this facility"
                )

            identifier.registry_system_name_search = normalized_new_name
            identifier.registry_system_name = encrypt_value(ce, dek_id, payload.registry_system_name)

        # 5️⃣ Update encrypted fields (ONLY if provided)
        if payload.identifier_value is not None:
            identifier.identifier_value = encrypt_value(ce, dek_id, payload.identifier_value)

        # 6️⃣ Timestamp
        identifier.updated_at = datetime.now(timezone.utc)

        await identifier.save()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="StateReportingIdentifiers",
                resource_id=str(identifier.id),
                status="success",
                notes="State reporting identifier updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "state_reporting_identifier_id": str(identifier.id),
            "message": "State reporting identifier updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating state reporting identifier"
        )