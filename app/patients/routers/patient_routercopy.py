from datetime import datetime, timezone, date
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key, encrypt_value_deterministic
from app.auth.password import hash_password
from app.accounts.models.user import UserRole
from app.utils.audit import log_audit
from app.schemas.patients.personal import PatientSchema, PersonalInfo, ContactInformation
from app.provider.models.providers import Provider
from beanie import PydanticObjectId
import json
import os
from app.patients.models.patients import PatientDoc
from app.patients.models.admissons import PatientAdmissionDoc
from bson import ObjectId
from beanie.operators import RegEx,Or
from typing import Annotated, Optional
from app.facility.models.beds import Beds

router = APIRouter(prefix="/patients", tags=["Patients-NEW"])


# @router.post("/create/{facility_id}/")
# async def create_patient(
#     facility_id: str,
#     payload: PatientSchema,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         # 1️⃣ Current user
#         admin_user = await UserDoc.get(current_user_id)
#         if not admin_user:
#             raise HTTPException(status_code=404, detail="User not found")

#         # 2️⃣ Encryption init
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce

#         dek_id = getattr(request.app, "dek_id", None)
#         if dek_id is None:
#             dek_id = ensure_data_key()
#             request.app.dek_id = dek_id

#         # 3️⃣ Facility validation
#         if not ObjectId.is_valid(facility_id):
#             raise HTTPException(status_code=400, detail="Invalid facility_id")

#         facility = await Facility.find_one(
#             Facility.id == ObjectId(facility_id),
#             Facility.created_by.id == admin_user.id,
#         )
#         if not facility:
#             raise HTTPException(status_code=403, detail="Facility access denied")

#         # 4️⃣ Provider validation
#         provider = await Provider.get(ObjectId(payload.provider_id))
#         if not provider:
#             raise HTTPException(status_code=404, detail="Provider not found")

#         # 5️⃣ Encrypt personal info
        


#         encrypted_pi = None
#         encrypted_ai = None
#         if payload.personal_information:
#             pi_json = json.dumps(
#                 payload.personal_information.model_dump(exclude_none=True),default=str
#             )
#             encrypted_pi = encrypt_value(ce, dek_id, pi_json)

#         # 6️⃣ Prepare contact info
#         if not payload.contact_information:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Contact information required to create patient user"
#             )

#         ci = payload.contact_information

#         if payload.admission_information:
#             ai_json = json.dumps(
#                 payload.admission_information.model_dump(exclude_none=True),default=str
#             )
#             encrypted_ai = encrypt_value(ce, dek_id, ai_json)


#         # 🔐 Hash password first
#         hashed_password = None
#         if ci.password:
#             hashed_password = hash_password(ci.password)

#         # 7️⃣ Create PATIENT UserDoc
#         patient_user = UserDoc(
#             full_name=encrypt_value(
#                 ce,
#                 dek_id,
#                 f"{payload.personal_information.first_name or ''} "
#                 f"{payload.personal_information.last_name or ''}".strip()
#             ),
#             email=encrypt_value(ce, dek_id, ci.email) if ci.email else None,
#             phone=encrypt_value(ce, dek_id, ci.phone_number) if ci.phone_number else None,
#             password=encrypt_value(ce, dek_id, hashed_password) if hashed_password else None,
#             role=encrypt_value(ce, dek_id, UserRole.PATIENT.value),

#             # 🔍 searchable (PLAIN TEXT)
#             full_name_search=f"{payload.personal_information.first_name or ''} "
#                              f"{payload.personal_information.last_name or ''}".lower(),
#             email_search=ci.email.lower() if ci.email else None,
#             phone_search=ci.phone_number if ci.phone_number else None,
#         )

#         await patient_user.insert()

#         # 8️⃣ Create PatientDoc
#         patient_doc = PatientDoc(
#             facility_id=facility,
#             provider_id=provider,
#             user_id=patient_user,   # 🔗 LINK
#             personal_information=encrypted_pi,
#             admisson_information=encrypted_ai,
#             created_by=admin_user,
#             created_at=datetime.now(timezone.utc),
#             updated_at=datetime.now(timezone.utc),
#         )

#         await patient_doc.insert()

#         return {
#             "success": True,
#             "patient_id": str(patient_doc.id),
#             "patient_user_id": str(patient_user.id),
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         print("❌ Crash:", e)
#         raise HTTPException(status_code=500, detail="Patient creation failed")



@router.post("/create/{facility_id}/")
async def create_patient(
    facility_id: str,
    payload: PatientSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # 1️⃣ Admin user
        admin_user = await UserDoc.get(current_user_id)
        if not admin_user:
            raise HTTPException(status_code=404, detail="User not found")

        # 2️⃣ Encryption init
        ce = getattr(request.app, "client_encryption", None) or init_encryption()
        request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None) or ensure_data_key()
        request.app.dek_id = dek_id

        # 3️⃣ Facility validation
        if not ObjectId.is_valid(facility_id):
            raise HTTPException(status_code=400, detail="Invalid facility_id")

        facility = await Facility.find_one(
            Facility.id == ObjectId(facility_id),
            Facility.created_by.id == admin_user.id,
        )
        if not facility:
            raise HTTPException(status_code=403, detail="Facility access denied")

        # 4️⃣ Provider validation
        provider = await Provider.get(ObjectId(payload.provider_id))
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        # 5️⃣ Bed validation ✅
        if not ObjectId.is_valid(payload.bed_id):
            raise HTTPException(status_code=400, detail="Invalid bed_id")

        bed = await Beds.find_one(
            Beds.id == ObjectId(payload.bed_id),
            Beds.facility_id.id == facility.id,
            Beds.is_deleted == False
        )

        if not bed:
            raise HTTPException(status_code=404, detail="Bed not found")

        if bed.bed_status_search == "occupied":
            raise HTTPException(status_code=400, detail="Bed already occupied")

        # 6️⃣ Encrypt Personal Info
        encrypted_pi = None
        if payload.personal_information:
            encrypted_pi = encrypt_value(
                ce,
                dek_id,
                payload.personal_information.model_dump_json(exclude_none=True)
            )

        # 7️⃣ Encrypt Admission Info
        encrypted_ai = None
        if payload.admission_information:
            encrypted_ai = encrypt_value(
                ce,
                dek_id,
                payload.admission_information.model_dump_json(exclude_none=True)
            )

        # 8️⃣ Encrypt Address Information (current + previous)
        encrypted_addr = None
        if payload.current_address or payload.previous_address:
            addr_payload = {
                "current_address": payload.current_address.model_dump(exclude_none=True) if payload.current_address else None,
                "previous_address": payload.previous_address.model_dump(exclude_none=True) if payload.previous_address else None,
            }
            addr_json = json.dumps(addr_payload, default=str)
            encrypted_addr = encrypt_value(ce, dek_id, addr_json)

        # 8️⃣ Contact info required
        if not payload.contact_information:
            raise HTTPException(status_code=400, detail="Contact information required")

        ci = payload.contact_information
        hashed_password = hash_password(ci.password) if ci.password else None

        encrypted_ins = None
        if (
            payload.medicare_information
            or payload.medicare_advantage
            or payload.primary_secondary_insurance
        ):
            ins_payload = {
                "medicare_information": payload.medicare_information.model_dump(exclude_none=True) if payload.medicare_information else None,
                "medicare_advantage": payload.medicare_advantage.model_dump(exclude_none=True) if payload.medicare_advantage else None,
                "primary_secondary_insurance": payload.primary_secondary_insurance.model_dump(exclude_none=True) if payload.primary_secondary_insurance else None,
            }
            ins_json = json.dumps(ins_payload, default=str)
            encrypted_ins = encrypt_value(ce, dek_id, ins_json)

        # 9️⃣ Create Patient User
        full_name = f"{payload.personal_information.first_name or ''} {payload.personal_information.last_name or ''}".strip()

        patient_user = UserDoc(
            full_name=encrypt_value(ce, dek_id, full_name),
            email=encrypt_value(ce, dek_id, ci.email) if ci.email else None,
            phone=encrypt_value(ce, dek_id, ci.phone_number) if ci.phone_number else None,
            password=encrypt_value(ce, dek_id, hashed_password) if hashed_password else None,
            role=encrypt_value(ce, dek_id, UserRole.PATIENT.value),

            full_name_search=full_name.lower(),
            email_search=ci.email.lower() if ci.email else None,
            phone_search=ci.phone_number if ci.phone_number else None,
        )

        await patient_user.insert()

        # 🔟 Create PatientDoc (🔥 bed_id assigned here)
        patient_doc = PatientDoc(
            facility_id=facility,
            bed_id=bed,                    # ✅ THIS IS THE ANSWER
            provider_id=provider,
            user_id=patient_user,
            personal_information=encrypted_pi,
            admisson_information=encrypted_ai,
            address_information=encrypted_addr,
            insurance_information=encrypted_ins,
            created_by=admin_user,
        )

        await patient_doc.insert()

        # 1️⃣1️⃣ Update bed status → OCCUPIED
        bed.bed_status_search = "occupied"
        bed.updated_at = datetime.now(timezone.utc)
        await bed.save()

        return {
            "success": True,
            "patient_id": str(patient_doc.id),
            "patient_user_id": str(patient_user.id),
            "bed_id": str(bed.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Patient creation failed")


# @router.get("/list/")
# async def get_all_patients(
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),

#     page: int = Query(1, ge=1),
#     page_size: int = Query(10, ge=1, le=100),

#     search: Optional[str] = Query(None),
#     status: Optional[str] = Query(None),
# ):
#     try:
#         # 1️⃣ User
#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         # 2️⃣ Encryption
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce

#         # ----------------------------
#         # 3️⃣ Query conditions (Beanie style)
#         # ----------------------------
#         conditions = [
#             PatientDoc.created_by.id == user.id,
#             PatientDoc.is_deleted == False
#         ]

#         if status:
#             conditions.append(PatientDoc.status == status.lower())

        
#         if search:
#             conditions.append(
#                 RegEx(PatientDoc.block_name_search, f"^{search.lower()}")
#             )

#         # ----------------------------
#         # 4️⃣ Pagination
#         # ----------------------------
#         skip = (page - 1) * page_size

#         # ----------------------------
#         # 5️⃣ Fetch data
#         # ----------------------------
#         patients = await (
#             PatientDoc.find(
#                 *conditions,
#                 fetch_links=True
#             )
#             .sort("-created_at")
#             .skip(skip)
#             .limit(page_size)
#             .to_list()
#         )

#         # ----------------------------
#         # 6️⃣ Total count (IMPORTANT)
#         # ----------------------------
#         total = await PatientDoc.find(*conditions).count()

#         # ----------------------------
#         # 7️⃣ Response
#         # ----------------------------
#         result = []
#         for patient in patients:
#             personal_info = None
#             if patient.personal_information:
#                 decrypted = decrypt_value(ce, patient.personal_information)
#                 personal_info = json.loads(decrypted)  # 🔥 IMPORTANT

#             result.append({
#                 "id": str(patient.id),
#                 "personal_information": personal_info,
                
#                 "facility_id": str(patient.facility_id.id) if patient.facility_id else None,
#                 "facility_name": (
#                     patient.facility_id.facility_name_search
#                     if patient.facility_id else None
#                 ),
#                 "status": patient.status,
#                 "created_at": patient.created_at,
#                 "updated_at": patient.updated_at,
#             })

#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Read",
#                 resource="Facility Campus Block",
#                 resource_id="LIST",
#                 status="success",
#                 notes=(
#                     f"Campus blocks fetched | "
#                     f"page={page}, page_size={page_size}, "
#                     f"search={search}, status={status}, "
#                     f"returned={len(result)}"
#                 ),
#             )
#         except Exception:
#             pass


#         return {
#             "success": True,
#             "page": page,
#             "page_size": page_size,
#             "total_pages": (total + page_size - 1) // page_size,
#             "count": len(result),
#             "total": total,
#             "data": result,
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         print("❌ Crash:", e)
#         raise HTTPException(status_code=500, detail="Internal Server Error")




@router.get("/list/")
async def get_all_patients(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    search: Optional[str] = Query(None),
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

        # 3️⃣ Conditions
        conditions = [
            PatientDoc.created_by.id == user.id,
            PatientDoc.is_deleted == False,
        ]

        # 🔍 Search by patient name (SAFE + FAST)
        if search:
            user_ids = await UserDoc.find(
                RegEx(UserDoc.full_name_search, f"^{search.lower()}")
            ).project(UserDoc.id).to_list()

            if user_ids:
                conditions.append(PatientDoc.user_id.id.in_(user_ids))
            else:
                return {
                    "success": True,
                    "page": page,
                    "page_size": page_size,
                    "total": 0,
                    "count": 0,
                    "data": [],
                }

        # 4️⃣ Pagination
        skip = (page - 1) * page_size

        # 5️⃣ Fetch
        patients = await (
            PatientDoc.find(*conditions, fetch_links=True)
            .sort("-created_at")
            .skip(skip)
            .limit(page_size)
            .to_list()
        )

        total = await PatientDoc.find(*conditions).count()

        # 6️⃣ Response
        result = []
        for patient in patients:
            personal_info = (
                json.loads(decrypt_value(ce, patient.personal_information))
                if patient.personal_information else None
            )
            admission_info = (
                json.loads(decrypt_value(ce, patient.admisson_information))
                if patient.admisson_information else None
            )

            # contact_info = (
            #     json.loads(decrypt_value(ce, patient.contact_information))
            #     if patient.contact_information else None
            # )
            result.append({
                "id": str(patient.id),
                "personal_information": personal_info,
                "admission_information": admission_info,
                "facility": {
                    "id": str(patient.facility_id.id),
                    "name": patient.facility_id.facility_name_search,
                } if patient.facility_id else None,
                "created_at": patient.created_at,
                "updated_at": patient.updated_at,
            })


        return {
            "success": True,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "count": len(result),
            "total": total,
            "patients": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch patients"
        )
