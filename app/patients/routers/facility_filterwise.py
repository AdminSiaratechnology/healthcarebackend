
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from app.facility.models.facility import Facility
from beanie.operators import RegEx, Or
from typing import Annotated, Optional
from app.facility.models.beds import Beds
from app.provider.models.providers import Provider
from app.encryption.encryption import init_encryption, ensure_data_key, decrypt_value
from app.auth.deps import get_current_user_id
from bson import ObjectId
import json
from app.accounts.models.user import UserDoc

router = APIRouter(prefix="/patients", tags=["Patients-NEW"])

@router.get("/facility-resources/{facility_id}")
async def get_facility_resources(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        # 1️⃣ Admin user
        admin_user = await UserDoc.get(current_user_id)
        if not admin_user:
            raise HTTPException(status_code=404, detail="User not found")
        # 1. Validation
        if not ObjectId.is_valid(facility_id):
             raise HTTPException(status_code=400, detail="Invalid facility_id")
             
        # 2. Encryption Init
        ce = getattr(request.app, "client_encryption", None) or init_encryption()
        request.app.client_encryption = ce
        
        # 3. Fetch Beds (Only available ones usually relevant for assignment, but fetching all active)
        # Using Beanie query with facility_id index
        beds = await Beds.find(
            Beds.facility_id.id == ObjectId(facility_id),
            Beds.is_deleted == False,
            fetch_links=True
        ).to_list()

        bed_list = []
        for bed in beds:
            # Decrypt bed number if encrypted
            bed_num = bed.bed_no_search  # Use searchable field first
            if not bed_num and bed.bed_number:
                try:
                    bed_num = decrypt_value(ce, bed.bed_number)
                except:
                    bed_num = "Unknown"
            
            bed_list.append({
                "id": str(bed.id),
                "bed_number": bed_num,
                "status": bed.bed_status_search or "available",
                "room_id": str(bed.room_id.id) if bed.room_id else None
            })

        # 4. Fetch Providers (Linked to this facility)
        # Providers have facility_ids list or primary_facility_id
        providers = await Provider.find(
             Or(
                Provider.facility_ids.id == ObjectId(facility_id),
                Provider.primary_facility_id.id == ObjectId(facility_id)
            ),
            Provider.is_deleted == False,
            fetch_links=True
        ).to_list()

        provider_list = []
        for prov in providers:
            # Decrypt Name
            first = ""
            last = ""
            try:
                if prov.first_name:
                    first = decrypt_value(ce, prov.first_name).strip('"')
                if prov.last_name:
                    last = decrypt_value(ce, prov.last_name).strip('"')
            except:
                pass
                
            full_name = f"{first} {last}".strip()
            
            provider_list.append({
                "id": str(prov.id),
                "name": full_name,
                "speciality": decrypt_value(ce, prov.speciality).strip('"') if prov.speciality else None
            })

        return {
            "success": True,
            "facility_id": facility_id,
            "beds": bed_list,
            "providers": provider_list
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching facility resources: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch facility resources")
