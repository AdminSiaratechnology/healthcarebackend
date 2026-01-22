from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File,Query
from pydantic import ValidationError
import re
from typing import Optional
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value,init_encryption,ensure_data_key,encrypt_value_deterministic,encrypt_dict,decrypt_value
from app.utils.audit import log_audit
from app.schemas.facilities.ITWorkstations import NetworkConfigSchema
from beanie import PydanticObjectId

import json
import os
from app.facility.models.network_config import NetworkConfig


router = APIRouter(prefix="/network-config", tags=["IT & Workstations"])



@router.post("/create/{facility_id}/")
async def create_facility_network_config(
    facility_id: str,
    payload: NetworkConfigSchema,
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

        # 4️⃣ Normalize primary_isp for duplicate/search (VERY IMPORTANT)
        if payload.primary_isp:
            normalized_primary_isp = payload.primary_isp.strip().lower()
        else:
            normalized_primary_isp = None

        # 5️⃣ Duplicate validation (ACTIVE RECORDS ONLY) — ek facility mein ek hi network config allowed
        existing = await NetworkConfig.find_one(
            NetworkConfig.facility_id.id == facility.id,
            NetworkConfig.primary_isp_search == normalized_primary_isp,
            NetworkConfig.is_deleted == False
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Network configuration already exists for this facility"
            )

        # Optional: agar primary_isp unique banana chahte ho to yeh add kar sakte ho
        # if normalized_primary_isp:
        #     duplicate_isp = await NetworkConfig.find_one(
        #         NetworkConfig.facility_id.id == facility.id,
        #         NetworkConfig.primary_isp_search == normalized_primary_isp,
        #         NetworkConfig.is_deleted == False
        #     )
        #     if duplicate_isp:
        #         raise HTTPException(400, "This primary ISP already configured for another facility")

        # 6️⃣ Encrypt fields
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "primary_isp": payload.primary_isp,
                "secondary_isp": payload.secondary_isp,
                "bandwidth": payload.bandwidth,
                "vpn_required": str(payload.vpn_required),  # bool ko string mein convert kiya
                "printer_routing_map": (
                    json.dumps(payload.printer_routing_map.model_dump())
                    if payload.printer_routing_map else None
                ),
            }
        )

        # 7️⃣ Save
        network_doc = NetworkConfig(
            facility_id=facility,
            created_by=user,
            
            primary_isp=encrypted["primary_isp"],
            secondary_isp=encrypted["secondary_isp"],
            bandwidth=encrypted["bandwidth"],
            vpn_required=encrypted["vpn_required"],
            printer_routing_map=encrypted["printer_routing_map"],
            
            # Searchable field
            primary_isp_search=normalized_primary_isp,
            
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await network_doc.insert()

        # 8️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="Network Config",
                resource_id=str(network_doc.id),
                status="success",
                notes="Facility network configuration created successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "facility_id_received": str(facility.id),
            "network_config_id": str(network_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating facility network config"
        )


@router.get("/list/")
async def get_facility_network_configs(
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
            NetworkConfig.created_by.id == user.id,
            NetworkConfig.is_deleted == False
        ]

        if status:
            conditions.append(NetworkConfig.status == status.lower())

        if search:
            search_value = search.lower()
            conditions.append(
                NetworkConfig.primary_isp_search == re.compile(f".*{search_value}.*", re.IGNORECASE)
                # partial match (contains) — practical hai ISP names ke liye
            )

        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------

        network_configs = await (
            NetworkConfig.find(
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
        total = await NetworkConfig.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------

        result = []
        for config in network_configs:
            printer_map_decrypted = None
            if config.printer_routing_map:
                try:
                    printer_map_decrypted = json.loads(decrypt_value(ce, config.printer_routing_map))
                except:
                    printer_map_decrypted = None

            result.append({
                "id": str(config.id),
                "primary_isp": decrypt_value(ce, config.primary_isp),
                "secondary_isp": decrypt_value(ce, config.secondary_isp),
                "bandwidth": decrypt_value(ce, config.bandwidth),
                "vpn_required": decrypt_value(ce, config.vpn_required) == "True",  # string se bool mein convert
                "printer_routing_map": printer_map_decrypted,
                
                "facility_id": str(config.facility_id.id) if config.facility_id else None,
                "facility_name": (
                    config.facility_id.facility_name_search
                    if config.facility_id else None
                ),
                "status": config.status,
                "created_at": config.created_at,
                "updated_at": config.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Network Configs",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility Network Configs fetched | "
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


@router.put("/update/{network_config_id}/")
async def update_facility_network_config(
    network_config_id: str,
    payload: NetworkConfigSchema,
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

        # 3️⃣ Get Network Config
        try:
            config_obj_id = ObjectId(network_config_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Network Config ID")

        config = await NetworkConfig.find_one(
            NetworkConfig.id == config_obj_id,
            NetworkConfig.created_by.id == user.id,
            NetworkConfig.is_deleted == False,
            fetch_links=True
        )

        if not config:
            raise HTTPException(status_code=404, detail="Network config not found")

        # 4️⃣ Normalize & check primary_isp (if changing)
        if payload.primary_isp is not None:
            normalized_primary_isp = payload.primary_isp.strip().lower()
            
            # Optional duplicate check (agar multiple configs allowed hain to yeh hata sakte ho)
            # duplicate = await NetworkConfig.find_one(
            #     NetworkConfig.facility_id.id == config.facility_id.id,
            #     NetworkConfig.primary_isp_search == normalized_primary_isp,
            #     NetworkConfig.id != config.id,
            #     NetworkConfig.is_deleted == False,
            # )
            # if duplicate:
            #     raise HTTPException(400, "This primary ISP is already in use")

            config.primary_isp_search = normalized_primary_isp
            config.primary_isp = encrypt_value(ce, dek_id, payload.primary_isp)

        # 5️⃣ Update encrypted fields (ONLY if provided)
        if payload.secondary_isp is not None:
            config.secondary_isp = encrypt_value(ce, dek_id, payload.secondary_isp)

        if payload.bandwidth is not None:
            config.bandwidth = encrypt_value(ce, dek_id, payload.bandwidth)

        if payload.vpn_required is not None:
            config.vpn_required = encrypt_value(ce, dek_id, str(payload.vpn_required))

        if payload.printer_routing_map is not None:
            config.printer_routing_map = encrypt_value(
                ce,
                dek_id,
                json.dumps(payload.printer_routing_map.model_dump())
            )

        # 6️⃣ Timestamp
        config.updated_at = datetime.now(timezone.utc)

        await config.save()

        # 7️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Network Config",
                resource_id=str(config.id),
                status="success",
                notes="Facility network config updated successfully",
            )
        except Exception:
            pass

        return {
            "success": True,
            "network_config_id": str(config.id),
            "message": "Facility network config updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating facility network config"
        )

