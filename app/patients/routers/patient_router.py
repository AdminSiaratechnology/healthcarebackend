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
from app.schemas.patients.personal import PatientSchema, PersonalInfo, ContactInformation, PatientUpdateSchema
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

        # if bed.bed_status_search == "occupied":
        #     raise HTTPException(status_code=400, detail="Bed already occupied")


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

        # 🔟 Encrypt Emergency Contact Information (primary + secondary)
        encrypted_ec = None
        if payload.emergency_contact or payload.secondary_emergency_contact:
            ec_payload = {
                "emergency_contact": payload.emergency_contact.model_dump(exclude_none=True) if payload.emergency_contact else None,
                "secondary_emergency_contact": payload.secondary_emergency_contact.model_dump(exclude_none=True) if payload.secondary_emergency_contact else None,
            }
            ec_json = json.dumps(ec_payload, default=str)
            encrypted_ec = encrypt_value(ce, dek_id, ec_json)

        # 11️⃣ Encrypt Diagnosis Information
        encrypted_diag = None
        if payload.diagnosis_information:
            diag_json = payload.diagnosis_information.model_dump_json(exclude_none=True)
            encrypted_diag = encrypt_value(ce, dek_id, diag_json)

        # 9️⃣ Create Patient User
        full_name = f"{payload.personal_information.first_name or ''} {payload.personal_information.last_name or ''}".strip()
       
        
        if ci.email:
            if await UserDoc.find_one(
                UserDoc.email_search == ci.email.lower()
            ):
                raise HTTPException(status_code=400, detail="Email already exists")
        
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
            emergency_contact_information=encrypted_ec,
            diagnosis=encrypted_diag,
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
            search_value = search.lower()
            conditions.append(
                Or(
                    RegEx(PatientDoc.user_id.full_name_search, f"^{search_value}"),
                    RegEx(PatientDoc.facility_id.facility_name_search, f"^{search_value}"),
                   
                    
                )
               
            )

           

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
            
            diagnosis_info = (
                json.loads(decrypt_value(ce, patient.diagnosis))
                if patient.diagnosis else None
            )

            address_info = (
                json.loads(decrypt_value(ce, patient.address_information))
                if patient.diagnosis else None
            )
            insurance_info = (
                json.loads(decrypt_value(ce, patient.insurance_information))
                if patient.diagnosis else None
            )
            contact_info = (
                json.loads(decrypt_value(ce, patient.emergency_contact_information))
                if patient.diagnosis else None
            )

           
            result.append({
                "id": str(patient.id),
                "full_name": patient.user_id.full_name_search if patient.user_id else None,
                "personal_information": personal_info,
                "admission_information": admission_info,
                "adrress_information": address_info,
                "insurance_information": insurance_info,
                "contact_information": contact_info,
                "diagnosis_information": diagnosis_info,
                "facility": {
                    "id": str(patient.facility_id.id),
                    "name": patient.facility_id.facility_name_search,
                } if patient.facility_id else None,
                "provider" :{
                    "id":str(patient.provider_id.id),
                    "name": patient.provider_id.user.id
                }if patient.provider_id else None,
                # "provider": {
                #     "id": str(patient.provider_id.id),
                #     "name": patient.provider_id.user.full_name_search,
                # } if patient.provider_id else None,
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





@router.put("/update/{patient_id}")
async def update_patient(
    patient_id: str,
    payload: PatientUpdateSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # -------------------------------------------------
        # 1️⃣ Auth user
        # -------------------------------------------------
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # -------------------------------------------------
        # 2️⃣ Encryption init
        # -------------------------------------------------
        ce = getattr(request.app, "client_encryption", None) or init_encryption()
        request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None) or ensure_data_key()
        request.app.dek_id = dek_id

        # -------------------------------------------------
        # 3️⃣ Fetch Patient (IMPORTANT: fetch_links=True)
        # -------------------------------------------------
        if not ObjectId.is_valid(patient_id):
            raise HTTPException(status_code=400, detail="Invalid patient_id")

        patient = await PatientDoc.find_one(
            PatientDoc.id == ObjectId(patient_id),
            PatientDoc.created_by.id == user.id,
            fetch_links=True
        )

        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found or access denied")

        update_data: dict = {}
        user_update_data: dict = {}

        # -------------------------------------------------
        # 🔧 Helper: merge + encrypt JSON fields
        # -------------------------------------------------
        def merge_encrypt(existing_binary, new_model):
            existing_data = {}
            if existing_binary:
                try:
                    existing_data = json.loads(decrypt_value(ce, existing_binary))
                except:
                    existing_data = {}

            new_data = new_model.model_dump(exclude_none=True)
            merged = {**existing_data, **new_data}
            encrypted = encrypt_value(ce, dek_id, json.dumps(merged, default=str))
            return merged, encrypted

        # -------------------------------------------------
        # 4️⃣ Bed Change
        # -------------------------------------------------
        if payload.bed_id:
            if not ObjectId.is_valid(payload.bed_id):
                raise HTTPException(status_code=400, detail="Invalid bed_id")

            if str(patient.bed_id.id) != payload.bed_id:
                new_bed = await Beds.find_one(
                    Beds.id == ObjectId(payload.bed_id),
                    Beds.facility_id.id == patient.facility_id.id,
                    Beds.is_deleted == False
                )

                if not new_bed:
                    raise HTTPException(status_code=404, detail="New bed not found")

                if new_bed.bed_status_search == "occupied":
                    raise HTTPException(status_code=400, detail="Bed already occupied")

                # Free old bed
                old_bed = await Beds.get(patient.bed_id.id)
                if old_bed:
                    old_bed.bed_status_search = "available"
                    old_bed.updated_at = datetime.now(timezone.utc)
                    await old_bed.save()

                # Occupy new bed
                new_bed.bed_status_search = "occupied"
                new_bed.updated_at = datetime.now(timezone.utc)
                await new_bed.save()

                update_data["bed_id"] = new_bed

        # -------------------------------------------------
        # 5️⃣ Provider
        # -------------------------------------------------
        if payload.provider_id:
            if not ObjectId.is_valid(payload.provider_id):
                raise HTTPException(status_code=400, detail="Invalid provider_id")

            provider = await Provider.get(ObjectId(payload.provider_id))
            if not provider:
                raise HTTPException(status_code=404, detail="Provider not found")

            update_data["provider_id"] = provider

        # -------------------------------------------------
        # 6️⃣ Personal Information + User Full Name
        # -------------------------------------------------
        if payload.personal_information:
            merged_pi, encrypted_pi = merge_encrypt(
                patient.personal_information,
                payload.personal_information
            )

            update_data["personal_information"] = encrypted_pi

            first_name = merged_pi.get("first_name", "") or ""
            last_name = merged_pi.get("last_name", "") or ""
            full_name = f"{first_name} {last_name}".strip()

            user_update_data["full_name"] = encrypt_value(ce, dek_id, full_name)
            user_update_data["full_name_search"] = full_name.lower()

        # -------------------------------------------------
        # 7️⃣ Contact Information → User
        # -------------------------------------------------
        if payload.contact_information:
            ci = payload.contact_information

            if ci.phone_number:
                user_update_data["phone"] = encrypt_value(ce, dek_id, ci.phone_number)
                user_update_data["phone_search"] = ci.phone_number

            if ci.email:
                user_update_data["email"] = encrypt_value(ce, dek_id, ci.email)
                user_update_data["email_search"] = ci.email.lower()

        # -------------------------------------------------
        # 8️⃣ Admission Information
        # -------------------------------------------------
        if payload.admission_information:
            _, encrypted_ai = merge_encrypt(
                patient.admisson_information,
                payload.admission_information
            )
            update_data["admisson_information"] = encrypted_ai

        # -------------------------------------------------
        # 9️⃣ Address Information
        # -------------------------------------------------
        if payload.current_address or payload.previous_address:
            existing_addr = {}
            if patient.address_information:
                try:
                    existing_addr = json.loads(decrypt_value(ce, patient.address_information))
                except:
                    existing_addr = {}

            if payload.current_address:
                existing_addr["current_address"] = payload.current_address.model_dump(exclude_none=True)

            if payload.previous_address:
                existing_addr["previous_address"] = payload.previous_address.model_dump(exclude_none=True)

            update_data["address_information"] = encrypt_value(
                ce, dek_id, json.dumps(existing_addr, default=str)
            )

        # -------------------------------------------------
        # 🔟 Insurance Information
        # -------------------------------------------------
        if (
            payload.medicare_information
            or payload.medicare_advantage
            or payload.primary_secondary_insurance
        ):
            existing_ins = {}
            if patient.insurance_information:
                try:
                    existing_ins = json.loads(decrypt_value(ce, patient.insurance_information))
                except:
                    existing_ins = {}

            if payload.medicare_information:
                existing_ins["medicare_information"] = payload.medicare_information.model_dump(exclude_none=True)

            if payload.medicare_advantage:
                existing_ins["medicare_advantage"] = payload.medicare_advantage.model_dump(exclude_none=True)

            if payload.primary_secondary_insurance:
                existing_ins["primary_secondary_insurance"] = payload.primary_secondary_insurance.model_dump(exclude_none=True)

            update_data["insurance_information"] = encrypt_value(
                ce, dek_id, json.dumps(existing_ins, default=str)
            )

        # -------------------------------------------------
        # 1️⃣1️⃣ Emergency Contact
        # -------------------------------------------------
        if payload.emergency_contact or payload.secondary_emergency_contact:
            existing_ec = {}
            if patient.emergency_contact_information:
                try:
                    existing_ec = json.loads(decrypt_value(ce, patient.emergency_contact_information))
                except:
                    existing_ec = {}

            if payload.emergency_contact:
                existing_ec["emergency_contact"] = payload.emergency_contact.model_dump(exclude_none=True)

            if payload.secondary_emergency_contact:
                existing_ec["secondary_emergency_contact"] = payload.secondary_emergency_contact.model_dump(exclude_none=True)

            update_data["emergency_contact_information"] = encrypt_value(
                ce, dek_id, json.dumps(existing_ec, default=str)
            )

        # -------------------------------------------------
        # 1️⃣2️⃣ Diagnosis
        # -------------------------------------------------
        if payload.diagnosis_information:
            _, encrypted_diag = merge_encrypt(
                patient.diagnosis,
                payload.diagnosis_information
            )
            update_data["diagnosis"] = encrypted_diag

        # -------------------------------------------------
        # 🧹 Clean None values
        # -------------------------------------------------
        update_data = {k: v for k, v in update_data.items() if v is not None}
        user_update_data = {k: v for k, v in user_update_data.items() if v is not None}

        # -------------------------------------------------
        # ✅ Save Patient
        # -------------------------------------------------
        if update_data:
            update_data["updated_at"] = datetime.now(timezone.utc)
            await patient.set(update_data)

        # -------------------------------------------------
        # ✅ Save User (Link already fetched)
        # -------------------------------------------------
        if user_update_data and patient.user_id:
            user_update_data["updated_at"] = datetime.now(timezone.utc)
            await patient.user_id.set(user_update_data)

        return {
            "success": True,
            "message": "Patient updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Update Crash:", e)
        raise HTTPException(status_code=500, detail="Patient update failed")






@router.get("/facility-resources/{facility_id}/")
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

        # Pateintes list filter by facility ids
        
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

        patients = await PatientDoc.find(
            PatientDoc.facility_id.id == ObjectId(facility_id),
            PatientDoc.is_deleted == False,
            fetch_links=True
        ).to_list()

        patient_list = []
        for p in patients:
            pname = None
            if p.user_id:
                try:
                    if getattr(p.user_id, "full_name_search", None):
                        pname = p.user_id.full_name_search
                    elif getattr(p.user_id, "full_name", None):
                        pname = decrypt_value(ce, p.user_id.full_name).strip('"')
                    
                except:
                    pname = None
            bnum = None
            if p.bed_id:
                try:
                    bnum = getattr(p.bed_id, "bed_no_search", None)
                    if not bnum and getattr(p.bed_id, "bed_number", None):
                        bnum = decrypt_value(ce, p.bed_id.bed_number)
                except:
                    bnum = None
            prov_name = None
            if p.provider_id:
                try:
                    f = decrypt_value(ce, p.provider_id.first_name).strip('"') if p.provider_id.first_name else ""
                    l = decrypt_value(ce, p.provider_id.last_name).strip('"') if p.provider_id.last_name else ""
                    prov_name = f"{f} {l}".strip()
                except:
                    prov_name = None
            def _dec_json(binval):
                try:
                    if not binval:
                        return None
                    s = decrypt_value(ce, binval)
                    try:
                        return json.loads(s) if isinstance(s, str) else s
                    except:
                        return s
                except:
                    return None
            user_email = None
            user_phone = None
            if p.user_id:
                try:
                    user_email = getattr(p.user_id, "email_search", None)
                    if not user_email and getattr(p.user_id, "email", None):
                        user_email = decrypt_value(ce, p.user_id.email).strip('"')
                except:
                    user_email = None
                try:
                    user_phone = getattr(p.user_id, "phone_search", None)
                    if not user_phone and getattr(p.user_id, "phone", None):
                        user_phone = decrypt_value(ce, p.user_id.phone).strip('"')
                except:
                    user_phone = None
            patient_list.append({
                "id": str(p.id),
                "name": pname,
                "bed_id": str(p.bed_id.id) if p.bed_id else None,
                "bed_number": bnum,
                "provider_id": str(p.provider_id.id) if p.provider_id else None,
                "provider_name": prov_name,
                "user_email": user_email,
                "user_phone": user_phone,
                "bed_status": getattr(p.bed_id, "bed_status_search", None) if p.bed_id else None,
                "personal_information": _dec_json(p.personal_information),
                "admission_information": _dec_json(p.admisson_information),
                "address_information": _dec_json(p.address_information),
                "insurance_information": _dec_json(p.insurance_information),
                "emergency_contact_information": _dec_json(p.emergency_contact_information),
                "diagnosis": _dec_json(p.diagnosis)
            })

        return {
            "success": True,
            "facility_id": facility_id,
            "beds": bed_list,
            "providers": provider_list,
            "patients": patient_list
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching facility resources: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch facility resources")
