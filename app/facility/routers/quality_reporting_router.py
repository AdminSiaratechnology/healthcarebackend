from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key,encrypt_dict
from app.utils.audit import log_audit
from app.schemas.facilities.quality import QualityReporting as QualityReportingSchema
from typing import Optional
from bson import ObjectId
from app.facility.models.quality_reporting import QualityReporting as QualityReportingDoc
from beanie.operators import In,RegEx,Or

router = APIRouter(prefix="/quality-reporting", tags=["Facility-Quality-Reporting"])




@router.post("/create/{facility_id}/")
async def create_quality_reporting(
    facility_id: str,
    payload: QualityReportingSchema,
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

        
        try:
            facility_obj_id = ObjectId(facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Facility ID format")
        

        # 3️⃣ Facility ownership check
        facility = await Facility.find_one({
            "_id": facility_obj_id,
            "created_by.$id": ObjectId(user.id),
            # "is_deleted": False
        })
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

       
        # 4️⃣ Normalize name (VERY IMPORTANT)
        normalized_organization_name = payload.organization_name.strip().lower()

       
       
        # 6️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        existing = await QualityReportingDoc.find_one({
            "facility_id.$id": facility.id,
            "organization_name_search" : normalized_organization_name,      
            "is_deleted": False
        })

        

        if existing:
            raise HTTPException(
                status_code=400,
                detail="already exists in this facility"
            )

        # 7️⃣ Random encryption (actual storage)
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "organization_name": payload.organization_name,
                "reporting_cadence": payload.reporting_cadence,
                
            }
        )

        # 8️⃣ Save
        quality_reporting = QualityReportingDoc(

            organization_name_search = normalized_organization_name,
            organization_name=encrypted["organization_name"],
            reporting_cadence=encrypted["reporting_cadence"],
            facility_id=facility,
            created_by=user,
            status="active",
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await quality_reporting.insert()

        # 9️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="CREATE",
                resource="quality reporting",
                resource_id=str(quality_reporting.id),
                status="success",
            )
        except Exception:
            pass

        return {
            "success": True,
            "quality_reporting_id": str(quality_reporting.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")


# @router.get("/get/quality-reporting/{facility_id}/")
# async def get_quality_reporting(
#     facility_id: str,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id)
# ):
#     try:
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()

#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         facility_obj = None
#         try:
#             facility_obj_id = PydanticObjectId(facility_id)
#             facility_obj = await Facility.get(facility_obj_id)
#         except Exception:
#             pass

#         if facility_obj is None:
#             facility_obj = await Facility.get(facility_id)
#         if not facility_obj:
#             raise HTTPException(status_code=404, detail="Facility not found")

        
#         # ---------------- ENCRYPTION ----------------
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce

#         # ---------------- QUALITY - REPORT ----------------
#         quality_rep = await QualityReportingDoc.find(
#             QualityReportingDoc.facility_id.id == facility_obj.id,
#             QualityReportingDoc.created_by.id == user.id
#         ).sort("-created_at").to_list()


#         # ---------------- RESPONSE ----------------


#         result = [
#             {
#                 "id": str(qr.id),
#                 "organization_name": _decrypt_value(ce, qr.organization_name),
#                 "reporting_cadence": _decrypt_value(ce, qr.reporting_cadence),
#                 "created_at": qr.created_at,
#                 "updated_at": qr.updated_at,
#             } for qr in quality_rep
#         ]

#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Read",
#                 resource="Quality Reporting",
#                 resource_id=str(facility_obj.id),
#                 status="success",
#                 notes="Quality reporting fetched",
#             )
#         except Exception:
#             pass

#         return result
#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(current_user_id),
#                 action="Read",
#                 resource="Quality Reporting",
#                 resource_id=facility_id,
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail=str(e))




@router.get("/list/")
async def get_quality_reporting(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    search: Optional[str] = Query(None),
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
            QualityReportingDoc.created_by.id == user.id,
            QualityReportingDoc.is_deleted == False
        ]

        if status:
            conditions.append(QualityReportingDoc.status == status.lower())

        if search:
            search_value = search.lower()
            conditions.append(
                Or(
                    RegEx(QualityReportingDoc.organization_name_search, f"^{search_value}"),
                    RegEx(QualityReportingDoc.facility_id.facility_name_search, f"^{search_value}"),
                    
                    
                )
               
            )

        
        
        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------
        quality_reporting = await (
            QualityReportingDoc.find(
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
        total = await QualityReportingDoc.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------
        result = []
        for reporting in quality_reporting:
            result.append({
                "id": str(reporting.id),
                "organization_name": decrypt_value(ce, reporting.organization_name),
                "reporting_cadence": decrypt_value(ce, reporting.reporting_cadence),
                "facility_id": str(reporting.facility_id.id) if reporting.facility_id else None,
                "facility_name": (
                    reporting.facility_id.facility_name_search
                    if reporting.facility_id else None
                ),
                "status": reporting.status,
                "created_at": reporting.created_at,
                "updated_at": reporting.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Facility Quality-Reporting",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Quality-Reporting fetched | "
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









@router.put("/update/{reporting_id}/")
async def update_quality_reporting(
    reporting_id: str,
    payload: QualityReportingSchema,  # all fields Optional jaise create mein
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

        # 3️⃣ Get Pharmacy
        try:
            quality_obj_id = ObjectId(reporting_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Quality Reporting ID")

        reporting = await QualityReportingDoc.find_one(
            QualityReportingDoc.id == quality_obj_id,
            QualityReportingDoc.created_by.id == user.id,
            QualityReportingDoc.is_deleted == False,
            fetch_links=True  # agar future mein facility details chahiye to
        )

        if not reporting:
            raise HTTPException(status_code=404, detail="quality reporting not found")

        # 4️⃣ Normalize & check duplicate pharmacy name (if name is being updated)
        if payload.organization_name:
            normalized_name = payload.organization_name.strip().lower()

            duplicate = await QualityReportingDoc.find_one(
                QualityReportingDoc.facility_id.id == reporting.facility_id.id,
                QualityReportingDoc.organization_name_search == normalized_name,
                QualityReportingDoc.id != reporting.id,
                QualityReportingDoc.is_deleted == False,
            )
            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="Quality Reporting name already exists in this facility"
                )

            reporting.organization_name_search = normalized_name
            reporting.organization_name = encrypt_value(
                ce, dek_id, payload.organization_name
            )

        # 5️⃣ Update encrypted fields (ONLY if provided)
        if payload.organization_name is not None:
            reporting.organization_name = encrypt_value(ce, dek_id, payload.organization_name)

        if payload.reporting_cadence is not None:
            reporting.reporting_cadence = encrypt_value(ce, dek_id, payload.reporting_cadence)

       
        # 6️⃣ Timestamp
        reporting.updated_at = datetime.now(timezone.utc)

        await reporting.save()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Quality Reporting",
                resource_id=str(reporting.id),
                status="success",
                notes="Pharmacy updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "quality_reporting_id": str(reporting.id),
            "message": "Quality Reporting updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating Quality Reporting"
        )