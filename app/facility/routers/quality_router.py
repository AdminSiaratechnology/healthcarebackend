from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key,encrypt_dict
from app.utils.audit import log_audit
from app.schemas.facilities.quality import QualitySchema
from bson import ObjectId
from app.facility.models.quality import QualityDoc
from typing import Optional
from beanie.operators import RegEx,Or,And

router = APIRouter(prefix="/quality", tags=["Facility-Quality"])



@router.post("/create/{facility_id}/")
async def create_quality(
    facility_id: str,
    payload: QualitySchema,
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

       

       
       
        # 6️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        existing = await QualityDoc.find_one({
            "facility_id.$id": facility.id,
            
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
                "enable_mds_reporting": payload.enable_mds_reporting,
                "enable_quality_measure": payload.enable_quality_measure,
                "enable_infection_control_tracking": payload.enable_infection_control_tracking,
                "fall_risk_program": payload.fall_risk_program,
            }
        )

        # 8️⃣ Save
        quality = QualityDoc(
            
            enable_mds_reporting=encrypted["enable_mds_reporting"],
            enable_quality_measure=encrypted["enable_quality_measure"],
            enable_infection_control_tracking=encrypted["enable_infection_control_tracking"],
            fall_risk_program=encrypted["fall_risk_program"],
            facility_id=facility,
            created_by=user,
            status="active",
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await quality.insert()

        # 9️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="CREATE",
                resource="quality",
                resource_id=str(quality.id),
                status="success",
            )
        except Exception:
            pass

        return {
            "success": True,
            "quality_id": str(quality.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")




@router.get("/list/")
async def get_quality(
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
            QualityDoc.created_by.id == user.id,
            QualityDoc.is_deleted == False
        ]

        if status:
            conditions.append(QualityDoc.status == status.lower())

        if search:
            search_value = search.lower()
            conditions.append(
                RegEx(QualityDoc.facility_id.facility_name_search, f"^{search_value}"),
               
            )
        
        
        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------
        qualities = await (
            QualityDoc.find(
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
        total = await QualityDoc.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------
        result = []
        for quality in qualities:
            result.append({
                "id": str(quality.id),
                "enable_mds_reporting": decrypt_value(ce, quality.enable_mds_reporting),
                "enable_quality_measure": decrypt_value(ce, quality.enable_quality_measure),
                "enable_infection_control_tracking": decrypt_value(ce, quality.enable_infection_control_tracking),
                "fall_risk_program": decrypt_value(ce, quality.fall_risk_program),
                "facility_id": str(quality.facility_id.id) if quality.facility_id else None,
                "facility_name": (
                    quality.facility_id.facility_name_search
                    if quality.facility_id else None
                ),
                "status": quality.status,
                "created_at": quality.created_at,
                "updated_at": quality.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Facility Quality",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Quality fetched | "
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






@router.put("/update/{quality_id}/")
async def update_breach_contact(
    quality_id: str,
    payload: QualitySchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # 1️⃣ User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 2️⃣ Encryption
        ce = getattr(request.app, "client_encryption", None) or init_encryption()
        request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None) or ensure_data_key()
        request.app.dek_id = dek_id

        # 3️⃣ Validate ID
        try:
            quality_obj_id = ObjectId(quality_id)
            
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Quality ID")

        # 4️⃣ Fetch block (Beanie-correct)
       
        quality = await QualityDoc.find_one(
            QualityDoc.id == quality_obj_id,
            QualityDoc.created_by.id == user.id,
            QualityDoc.is_deleted == False,
        )
        

        

        if not quality:
            raise HTTPException(status_code=404, detail="Quality not found")

       

       

        # 7️⃣ Encrypt & update
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "enable_mds_reporting": payload.enable_mds_reporting,
                "enable_quality_measure": payload.enable_quality_measure,
                "enable_infection_control_tracking": payload.enable_infection_control_tracking,
                "fall_risk_program": payload.fall_risk_program,
            }
        )

        quality.enable_mds_reporting = encrypted["enable_mds_reporting"]
        quality.enable_quality_measure = encrypted["enable_quality_measure"]
        quality.enable_infection_control_tracking = encrypted["enable_infection_control_tracking"]
        quality.fall_risk_program = encrypted["fall_risk_program"]
        quality.updated_at = datetime.now(timezone.utc)

        await quality.save()

        # Audit log
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Facility Quality",
                resource_id=str(quality.id),
                status="success",
                notes="Quality updated successfully",
            )
        except Exception:
            pass


        return {
            "success": True,
            "quality_id": str(quality.id),
            "updated_at": quality.updated_at,
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Update",
                resource="Facility Quality",
                resource_id=str(quality_id),
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error")

