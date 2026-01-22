from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value,init_encryption,ensure_data_key,encrypt_value_deterministic,encrypt_dict,decrypt_value
from app.utils.audit import log_audit
from app.schemas.facilities.ITWorkstations import DeviceInventorySchema
from beanie import PydanticObjectId
from bson import ObjectId
import json
import os
from app.facility.models.DeviceInventory import DeviceInventory
from typing import Optional
import re
router = APIRouter(prefix="/device-inventory", tags=["IT & Workstations"])



@router.post("/create/{facility_id}/")
async def create_facility_device_inventory(
    facility_id: str,
    payload: DeviceInventorySchema,
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

        # 4️⃣ Validate required fields
        if not payload.device_type or not payload.count:
            raise HTTPException(
                status_code=400,
                detail="Device type and count are required"
            )

        # 5️⃣ Normalize for searchable field & duplicate check
        normalized_device_type = payload.device_type.value.strip().lower()

        existing = await DeviceInventory.find_one(
            DeviceInventory.facility_id.id == facility.id,
            DeviceInventory.device_type_search == normalized_device_type,
            DeviceInventory.is_deleted == False
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Inventory entry for this device type already exists in this facility"
            )

        # 6️⃣ Encrypt fields
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "device_type": payload.device_type.value,
                "counts": str(payload.count),
                "operating_system": payload.operating_system.value if payload.operating_system else None,
            }
        )

        # 7️⃣ Save
        device_doc = DeviceInventory(
            facility_id=facility,
            created_by=user,
            
            device_type=encrypted["device_type"],
            counts=encrypted["counts"],
            operating_system=encrypted["operating_system"],
            
            device_type_search=normalized_device_type,
            
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await device_doc.insert()

        # 8️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Device Inventory",
                resource_id=str(device_doc.id),
                status="success",
                notes="Facility device inventory entry created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "device_inventory_id": str(device_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility device inventory"
        )


@router.get("/list/")
async def get_facility_device_inventory(
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
            DeviceInventory.created_by.id == user.id,
            DeviceInventory.is_deleted == False
        ]

        if status:
            conditions.append(DeviceInventory.status == status.lower())

        if search:
            search_value = search.lower()
            conditions.append(
                DeviceInventory.device_type_search == re.compile(f".*{search_value}.*", re.IGNORECASE)
            )

        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------

        devices = await (
            DeviceInventory.find(
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
        total = await DeviceInventory.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------

        result = []
        for dev in devices:
            result.append({
                "id": str(dev.id),
                "device_type": decrypt_value(ce, dev.device_type),
                "count": int(decrypt_value(ce, dev.counts)) if dev.counts else None,
                "operating_system": decrypt_value(ce, dev.operating_system),
                
                "facility_id": str(dev.facility_id.id) if dev.facility_id else None,
                
                "status": dev.status,
                "created_at": dev.created_at,
                "updated_at": dev.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Device Inventory",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Device Inventory fetched | "
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


        
@router.put("/update/{device_inventory_id}/")
async def update_facility_device_inventory(
    device_inventory_id: str,
    payload: DeviceInventorySchema,
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

        # 3️⃣ Get Device Inventory
        try:
            dev_obj_id = ObjectId(device_inventory_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Device Inventory ID")

        dev = await DeviceInventory.find_one(
            DeviceInventory.id == dev_obj_id,
            DeviceInventory.created_by.id == user.id,
            DeviceInventory.is_deleted == False,
            fetch_links=True
        )

        if not dev:
            raise HTTPException(status_code=404, detail="Device inventory entry not found")

        # 4️⃣ Normalize & duplicate check if device_type is changing
        if payload.device_type is not None:
            normalized_new_type = payload.device_type.value.strip().lower()

            duplicate = await DeviceInventory.find_one(
                DeviceInventory.facility_id.id == dev.facility_id.id,
                DeviceInventory.device_type_search == normalized_new_type,
                DeviceInventory.id != dev.id,
                DeviceInventory.is_deleted == False,
            )
            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="Another inventory entry with this device type already exists"
                )

            dev.device_type_search = normalized_new_type
            dev.device_type = encrypt_value(ce, dek_id, payload.device_type.value)

        # 5️⃣ Update encrypted fields (ONLY if provided)
        if payload.count is not None:
            dev.counts = encrypt_value(ce, dek_id, str(payload.count))

        if payload.operating_system is not None:
            dev.operating_system = encrypt_value(ce, dek_id, payload.operating_system.value)

        # 6️⃣ Timestamp
        dev.updated_at = datetime.now(timezone.utc)

        await dev.save()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Device Inventory",
                resource_id=str(dev.id),
                status="success",
                notes="Facility device inventory updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "device_inventory_id": str(dev.id),
            "message": "Facility device inventory updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating facility device inventory"
        )