from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.facilities.standards import FacilityStandardsSchema
from beanie import PydanticObjectId
from bson import ObjectId
import json
import os
from app.facility.models.standards import StandardsDoc
import re
from typing import Optional



router = APIRouter(prefix="/standards", tags=["Standards"])


# @router.post("/create/standards/{facility_id}/")
# async def create_standards(
#     facility_id: str,
#     standards: FacilityStandardsSchema,
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

#         doc = StandardsDoc(
#             facility_id=facility,
#             diagnosis_coding=enc_json_or_none(standards.diagnosis_coding),
#             procedure_coding=enc_json_or_none(standards.procedure_coding),
#             laboratory_coding=enc_json_or_none(standards.laboratory_coding),
#             allergy_coding=enc_json_or_none(standards.allergy_coding),
#             terminology_update=enc_json_or_none(standards.terminology_update),
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
#                 resource="Standards",
#                 resource_id=str(doc.id),
#                 status="success",
#                 notes="Facility standards created successfully",
#             )
#         except Exception:
#             pass

#         return {
#             "success": True,
#             "facility_id_received": str(facility.id),
#             "standards_id": str(doc.id),
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(current_user_id),
#                 action="Create",
#                 resource="Standards",
#                 resource_id="N/A",
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail="Internal Server Error while creating standards")


@router.post("/create/{facility_id}/")
async def create_facility_standards(
    facility_id: str,
    payload: FacilityStandardsSchema,
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

        try:
            facility_obj_id = ObjectId(facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")

        facility = await Facility.find_one(
            Facility.id == facility_obj_id,
            Facility.created_by.id == user.id,
            # Facility.is_deleted == False,
        )
        if not facility:
            raise HTTPException(
                status_code=404,
                detail="Facility not found or you don't have permission"
            )

        # 4️⃣ Check if standards already exist for this facility (ONE-TO-ONE)
        existing = await StandardsDoc.find_one(
            StandardsDoc.facility_id.id == facility.id,
            StandardsDoc.is_deleted == False
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Standards configuration already exists for this facility. You can only have one per facility."
            )

        # 5️⃣ Custom serializer for date/datetime objects (if any future fields added)
        def date_serializer(obj):
            if isinstance(obj, date):
                return obj.isoformat()
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")

        # 6️⃣ Encrypt each section separately (JSON string)
        diagnosis_enc = None
        if payload.diagnosis_coding:
            diagnosis_json = json.dumps(payload.diagnosis_coding.model_dump(), default=date_serializer)
            diagnosis_enc = encrypt_value(ce, dek_id, diagnosis_json)

        procedure_enc = None
        if payload.procedure_coding:
            procedure_json = json.dumps(payload.procedure_coding.model_dump(), default=date_serializer)
            procedure_enc = encrypt_value(ce, dek_id, procedure_json)

        laboratory_enc = None
        if payload.laboratory_coding:
            laboratory_json = json.dumps(payload.laboratory_coding.model_dump(), default=date_serializer)
            laboratory_enc = encrypt_value(ce, dek_id, laboratory_json)

        allergy_enc = None
        if payload.allergy_coding:
            allergy_json = json.dumps(payload.allergy_coding.model_dump(), default=date_serializer)
            allergy_enc = encrypt_value(ce, dek_id, allergy_json)

        terminology_enc = None
        if payload.terminology_update:
            terminology_json = json.dumps(payload.terminology_update.model_dump(), default=date_serializer)
            terminology_enc = encrypt_value(ce, dek_id, terminology_json)

        # 7️⃣ Save
        standards_doc = StandardsDoc(
            facility_id=facility,
            created_by=user,
            
            diagnosis_coding=diagnosis_enc,
            procedure_coding=procedure_enc,
            laboratory_coding=laboratory_enc,
            allergy_coding=allergy_enc,
            terminology_update=terminology_enc,
            
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await standards_doc.insert()

        # 8️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Facility Standards",
                resource_id=str(standards_doc.id),
                status="success",
                notes="Facility standards configuration created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "standards_id": str(standards_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility standards"
        )




# @router.get("/get/standards/{facility_id}/")
# async def get_standards(
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

#     # ---------------- STANDARD  ----------------
#     standard = await StandardsDoc.find(
#         StandardsDoc.facility_id.id == facility_obj.id,
#         StandardsDoc.created_by.id == user.id
#     ).sort("-created_at").to_list()


#     # ---------------- RESPONSE ----------------



#     result = [
#         {
#             "id": str(sd.id),
#             "diagnosis_coding": _decrypt_json_field(ce, sd.diagnosis_coding),
#             "procedure_coding": _decrypt_json_field(ce, sd.procedure_coding),
#             "laboratory_coding": _decrypt_json_field(ce, sd.laboratory_coding),
#             "allergy_coding": _decrypt_json_field(ce, sd.allergy_coding),
#             "terminology_update": _decrypt_json_field(ce, sd.terminology_update),
#             "created_at": sd.created_at,
#             "updated_at": sd.updated_at,
#         } for sd in standard
#     ]

#     try:
#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Read",
#             resource="Standards",
#             resource_id=str(facility_obj.id),
#             status="success",
#             notes="Facility standards fetched successfully",
#         )
#     except Exception:
#         pass

#     return result



@router.get("/list/")
async def get_facility_standards(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    status: Optional[str] = Query(None, description="Filter by status (active/inactive)"),

    search: Optional[str] = Query(None, description="Search by facility name or code"),
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
        # 3️⃣ Query conditions
        # ----------------------------
        conditions = [
            StandardsDoc.created_by.id == user.id,
            StandardsDoc.is_deleted == False
        ]

        if status:
            conditions.append(StandardsDoc.status == status.lower())
        
        if search:
            search_value = search.lower()
            # Search facility name via linked Facility model
            conditions.append(
                StandardsDoc.facility_id.facility_name_search == re.compile(f".*{search_value}.*", re.IGNORECASE)
            )
        

        # ----------------------------
        # 4️⃣ Pagination (though usually 0 or 1 record per facility)
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------

        standards_list = await (
            StandardsDoc.find(
                *conditions,
                fetch_links=True
            )
            .sort("-created_at")
            .skip(skip)
            .limit(page_size)
            .to_list()
        )

        # ----------------------------
        # 6️⃣ Total count
        # ----------------------------
        total = await StandardsDoc.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response (decrypt each JSON section)
        # ----------------------------

        result = []
        for std in standards_list:
            # Decrypt each section if exists
            diagnosis_dec = None
            if std.diagnosis_coding:
                try:
                    diag_json = decrypt_value(ce, std.diagnosis_coding)
                    diagnosis_dec = json.loads(diag_json)
                except:
                    diagnosis_dec = None

            procedure_dec = None
            if std.procedure_coding:
                try:
                    proc_json = decrypt_value(ce, std.procedure_coding)
                    procedure_dec = json.loads(proc_json)
                except:
                    procedure_dec = None

            laboratory_dec = None
            if std.laboratory_coding:
                try:
                    lab_json = decrypt_value(ce, std.laboratory_coding)
                    laboratory_dec = json.loads(lab_json)
                except:
                    laboratory_dec = None

            allergy_dec = None
            if std.allergy_coding:
                try:
                    allergy_json = decrypt_value(ce, std.allergy_coding)
                    allergy_dec = json.loads(allergy_json)
                except:
                    allergy_dec = None

            terminology_dec = None
            if std.terminology_update:
                try:
                    term_json = decrypt_value(ce, std.terminology_update)
                    terminology_dec = json.loads(term_json)
                except:
                    terminology_dec = None

            result.append({
                "id": str(std.id),
                "facility_id": str(std.facility_id.id) if std.facility_id else None,
                "facility_name": (
                    std.facility_id.facility_name_search
                    if std.facility_id else None
                ),
                "diagnosis_coding": diagnosis_dec,
                "procedure_coding": procedure_dec,
                "laboratory_coding": laboratory_dec,
                "allergy_coding": allergy_dec,
                "terminology_update": terminology_dec,
                "status": std.status,
                "created_at": std.created_at,
                "updated_at": std.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Facility Standards",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Standards fetched | "
                    f"page={page}, page_size={page_size}, "
                    f"status={status}, returned={len(result)}"
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


@router.put("/update/{standards_id}/")
async def update_facility_standards(
    standards_id: str,
    payload: FacilityStandardsSchema,
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

        # 3️⃣ Get Standards config
        try:
            std_obj_id = ObjectId(standards_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Standards ID")

        std = await StandardsDoc.find_one(
            StandardsDoc.id == std_obj_id,
            StandardsDoc.created_by.id == user.id,
            StandardsDoc.is_deleted == False,
            fetch_links=True
        )

        if not std:
            raise HTTPException(status_code=404, detail="Facility standards configuration not found")

        # 4️⃣ Custom serializer for date/datetime (future-proof)
        def date_serializer(obj):
            if isinstance(obj, date):
                return obj.isoformat()
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")

        # 5️⃣ Partial update - encrypt only provided sections
        if payload.diagnosis_coding is not None:
            diag_json = json.dumps(payload.diagnosis_coding.model_dump(), default=date_serializer)
            std.diagnosis_coding = encrypt_value(ce, dek_id, diag_json)

        if payload.procedure_coding is not None:
            proc_json = json.dumps(payload.procedure_coding.model_dump(), default=date_serializer)
            std.procedure_coding = encrypt_value(ce, dek_id, proc_json)

        if payload.laboratory_coding is not None:
            lab_json = json.dumps(payload.laboratory_coding.model_dump(), default=date_serializer)
            std.laboratory_coding = encrypt_value(ce, dek_id, lab_json)

        if payload.allergy_coding is not None:
            allergy_json = json.dumps(payload.allergy_coding.model_dump(), default=date_serializer)
            std.allergy_coding = encrypt_value(ce, dek_id, allergy_json)

        if payload.terminology_update is not None:
            term_json = json.dumps(payload.terminology_update.model_dump(), default=date_serializer)
            std.terminology_update = encrypt_value(ce, dek_id, term_json)

        # 6️⃣ Timestamp
        std.updated_at = datetime.now(timezone.utc)

        await std.save()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Facility Standards",
                resource_id=str(std.id),
                status="success",
                notes="Facility standards configuration updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "standards_id": str(std.id),
            "message": "Facility standards updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating facility standards"
        )