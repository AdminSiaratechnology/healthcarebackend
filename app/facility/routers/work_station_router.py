from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value,init_encryption,ensure_data_key,encrypt_value_deterministic,encrypt_dict,decrypt_value
from app.utils.audit import log_audit
from app.schemas.facilities.ITWorkstations import WorkStationSchema
from beanie import PydanticObjectId
import re
from bson import ObjectId
import json
import os
from app.facility.models.workstations import WorkStation
from typing import Optional


router = APIRouter(prefix="/workstations", tags=["IT & Workstations"])


@router.post("/create/{facility_id}/")
async def create_facility_workstation(
    facility_id: str,
    payload: WorkStationSchema,
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
            raise HTTPException(status_code=404, detail="Facility not found or you don't have permission")

        # 4️⃣ Normalize workstation_code (VERY IMPORTANT)
        if payload.work_station_code:
            normalized_code = payload.work_station_code.strip().lower()
        else:
            normalized_code = None

        # 5️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        if normalized_code:
            existing = await WorkStation.find_one(
                WorkStation.facility_id.id == facility.id,
                WorkStation.workstation_code_search == normalized_code,
                WorkStation.is_deleted == False
            )
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail="Workstation with this code already exists in this facility"
                )

        # 6️⃣ Encrypt fields
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "workstation_code": payload.work_station_code,
                "location": payload.location,
                "operating_system": payload.os_type.value if payload.os_type else None,
                "peripherals": (
                    json.dumps(payload.peripherals.model_dump())
                    if payload.peripherals else None
                ),
            }
        )

        # 7️⃣ Save
        workstation_doc = WorkStation(
            facility_id=facility,
            created_by=user,
            
            workstation_code=encrypted["workstation_code"],
            location=encrypted["location"],
            operating_system=encrypted["operating_system"],
            peripherals=encrypted["peripherals"],
            
            workstation_code_search=normalized_code,
            
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await workstation_doc.insert()

        # 8️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="WorkStation",
                resource_id=str(workstation_doc.id),
                status="success",
                notes="Facility workstation created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "workstation_id": str(workstation_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility workstation"
        )


@router.get("/list/")
async def get_facility_workstations(
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
            WorkStation.created_by.id == user.id,
            WorkStation.is_deleted == False
        ]

        if status:
            conditions.append(WorkStation.status == status.lower())

        if search:
            search_value = search.lower()
            conditions.append(
                WorkStation.workstation_code_search == re.compile(f".*{search_value}.*", re.IGNORECASE)
            )

        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------

        workstations = await (
            WorkStation.find(
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
        total = await WorkStation.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------

        result = []
        for ws in workstations:
            peripherals_decrypted = None
            if ws.peripherals:
                try:
                    peripherals_decrypted = json.loads(decrypt_value(ce, ws.peripherals))
                except:
                    peripherals_decrypted = None

            result.append({
                "id": str(ws.id),
                "work_station_code": decrypt_value(ce, ws.workstation_code),
                "location": decrypt_value(ce, ws.location),
                "operating_system": decrypt_value(ce, ws.operating_system),
                "peripherals": peripherals_decrypted,
                
                "facility_id": str(ws.facility_id.id) if ws.facility_id else None,
                "facility_name": (
                    ws.facility_id.facility_name_search
                    if ws.facility_id else None
                ),
                
                "status": ws.status,
                "created_at": ws.created_at,
                "updated_at": ws.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="WorkStations",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility WorkStations fetched | "
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


@router.put("/update/{workstation_id}/")
async def update_facility_workstation(
    workstation_id: str,
    payload: WorkStationSchema,
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

        # 3️⃣ Get Workstation
        try:
            ws_obj_id = ObjectId(workstation_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Workstation ID")

        ws = await WorkStation.find_one(
            WorkStation.id == ws_obj_id,
            WorkStation.created_by.id == user.id,
            WorkStation.is_deleted == False,
            fetch_links=True
        )

        if not ws:
            raise HTTPException(status_code=404, detail="Workstation not found")

        # 4️⃣ Normalize & check duplicate workstation_code (if changing)
        if payload.work_station_code is not None:
            normalized_code = payload.work_station_code.strip().lower()

            duplicate = await WorkStation.find_one(
                WorkStation.facility_id.id == ws.facility_id.id,
                WorkStation.workstation_code_search == normalized_code,
                WorkStation.id != ws.id,
                WorkStation.is_deleted == False,
            )
            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="Workstation with this code already exists in this facility"
                )

            ws.workstation_code_search = normalized_code
            ws.workstation_code = encrypt_value(ce, dek_id, payload.work_station_code)

        # 5️⃣ Update encrypted fields (ONLY if provided)
        if payload.location is not None:
            ws.location = encrypt_value(ce, dek_id, payload.location)

        if payload.os_type is not None:
            ws.operating_system = encrypt_value(ce, dek_id, payload.os_type.value)

        if payload.peripherals is not None:
            ws.peripherals = encrypt_value(
                ce,
                dek_id,
                json.dumps(payload.peripherals.model_dump())
            )

        # 6️⃣ Timestamp
        ws.updated_at = datetime.now(timezone.utc)

        await ws.save()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="WorkStation",
                resource_id=str(ws.id),
                status="success",
                notes="Facility workstation updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "workstation_id": str(ws.id),
            "message": "Facility workstation updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating facility workstation"
        )