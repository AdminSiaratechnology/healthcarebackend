from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value,init_encryption,ensure_data_key,encrypt_value_deterministic,encrypt_dict,decrypt_value
from app.utils.audit import log_audit
from app.schemas.facilities.ITWorkstations import WifiNetworkSchema
from beanie import PydanticObjectId
from bson import ObjectId
import json
import os
from app.facility.models.wifi_network import WifiNetwork
import re
from typing import Optional

router = APIRouter(prefix="/wifi", tags=["Wifi-Network"])


@router.post("/create/{facility_id}/")
async def create_facility_wifi_network(
    facility_id: str,
    payload: WifiNetworkSchema,
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

        # 4️⃣ Normalize SSID (VERY IMPORTANT)
        if payload.ssid:
            normalized_ssid = payload.ssid.strip().lower()
        else:
            normalized_ssid = None

        # 5️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        # Ek facility mein same SSID duplicate nahi hona chahiye
        if normalized_ssid:
            existing = await WifiNetwork.find_one(
                WifiNetwork.facility_id.id == facility.id,
                WifiNetwork.ssid_search == normalized_ssid,
                WifiNetwork.is_deleted == False
            )
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail="WiFi network with this SSID already exists in this facility"
                )

        # 6️⃣ Encrypt fields
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "ssid": payload.ssid,
                "password": payload.password,
                "guest_network": str(payload.guest_network),  # bool → string
            }
        )

        # 7️⃣ Save
        wifi_doc = WifiNetwork(
            facility_id=facility,
            created_by=user,
            
            ssid=encrypted["ssid"],
            password=encrypted["password"],
            guest_network=encrypted["guest_network"],
            
            ssid_search=normalized_ssid,
            
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await wifi_doc.insert()

        # 8️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Wifi Network",
                resource_id=str(wifi_doc.id),
                status="success",
                notes="Facility WiFi network created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "wifi_network_id": str(wifi_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility wifi network"
        )




@router.get("/list/")
async def get_facility_wifi_networks(
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
            WifiNetwork.created_by.id == user.id,
            WifiNetwork.is_deleted == False
        ]

        if status:
            conditions.append(WifiNetwork.status == status.lower())

        if search:
            search_value = search.lower()
            conditions.append(
                WifiNetwork.ssid_search == re.compile(f".*{search_value}.*", re.IGNORECASE)
            )

        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------

        wifi_networks = await (
            WifiNetwork.find(
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
        total = await WifiNetwork.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------

        result = []
        for wifi in wifi_networks:
            result.append({
                "id": str(wifi.id),
                "ssid": decrypt_value(ce, wifi.ssid),
                "password": decrypt_value(ce, wifi.password),  # sensitive, lekin agar frontend ko chahiye to
                "guest_network": decrypt_value(ce, wifi.guest_network) == "True",
                
                "facility_id": str(wifi.facility_id.id) if wifi.facility_id else None,
                "facility_name": (
                    wifi.facility_id.facility_name_search
                    if wifi.facility_id else None
                ),
                "status": wifi.status,
                "created_at": wifi.created_at,
                "updated_at": wifi.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Wifi Networks",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Wifi Networks fetched | "
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



@router.put("/update/{wifi_network_id}/")
async def update_facility_wifi_network(
    wifi_network_id: str,
    payload: WifiNetworkSchema,
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

        # 3️⃣ Get Wifi Network
        try:
            wifi_obj_id = ObjectId(wifi_network_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Wifi Network ID")

        wifi = await WifiNetwork.find_one(
            WifiNetwork.id == wifi_obj_id,
            WifiNetwork.created_by.id == user.id,
            WifiNetwork.is_deleted == False,
            fetch_links=True
        )

        if not wifi:
            raise HTTPException(status_code=404, detail="Wifi network not found")

        # 4️⃣ Normalize & check duplicate SSID (if changing)
        if payload.ssid is not None:
            normalized_ssid = payload.ssid.strip().lower()

            duplicate = await WifiNetwork.find_one(
                WifiNetwork.facility_id.id == wifi.facility_id.id,
                WifiNetwork.ssid_search == normalized_ssid,
                WifiNetwork.id != wifi.id,
                WifiNetwork.is_deleted == False,
            )
            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="Wifi network with this SSID already exists in this facility"
                )

            wifi.ssid_search = normalized_ssid
            wifi.ssid = encrypt_value(ce, dek_id, payload.ssid)

        # 5️⃣ Update encrypted fields (ONLY if provided)
        if payload.password is not None:
            wifi.password = encrypt_value(ce, dek_id, payload.password)

        if payload.guest_network is not None:
            wifi.guest_network = encrypt_value(ce, dek_id, str(payload.guest_network))

        # 6️⃣ Timestamp
        wifi.updated_at = datetime.now(timezone.utc)

        await wifi.save()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Wifi Network",
                resource_id=str(wifi.id),
                status="success",
                notes="Facility wifi network updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "wifi_network_id": str(wifi.id),
            "message": "Facility wifi network updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating facility wifi network"
        )