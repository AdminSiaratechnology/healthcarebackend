

from beanie import PydanticObjectId, Link
from fastapi import APIRouter, Request, HTTPException, Depends, Form, File, UploadFile, Query
from pydantic import EmailStr
from enum import Enum
from datetime import datetime, timezone
from bson import ObjectId
import boto3
from typing import Optional
from beanie.operators import RegEx,Or,And,In
from app.auth.deps import get_current_user_id
from app.accounts.models.user import UserDoc, UserRole
from app.facility.models.facility import Facility
from app.provider.models.providers import Provider
from app.schedule.models.schedule import ScheduleDoc
from app.patients.models.patients import PatientDoc
from app.facility.models.beds import Beds
from app.facility.models.facility_rooms import FacilityRooms
from app.scheduler.models import Scheduler
from app.auth.password import hash_password
from app.encryption.encryption import (
    encrypt_value,
    encrypt_value_deterministic,
    encrypt_dict,
    init_encryption,
    ensure_data_key,
    decrypt_value,
    safe_decrypt_list,
    
)
from app.utils.audit import log_audit
from app.utils.s3_utils import put_object, safe_filename, get_bucket_name
import json
from app.database.config import settings
from botocore.config import Config
from typing import List

router = APIRouter(prefix="/providers", tags=["Providers"])


# ========================= ENUMS ========================= #

class DegreeEnum(str, Enum):
    MD = "MD- Doctor of Medicine"
    DO = "DO-Doctor of Osteopathic Medicine"
    NP = "Nurse Practitioner"
    PA = "Physicain Assistant"


class Speciality(str, Enum):
    InternalMedicine = "Internal Medicine"
    FamilyMedicine = "Family Medicine"
    Cardiology = "Cardiology"
    GeriatricMedicine = "Geriatric Medicine"
    EmergencyMedicine = "Emergency Medicine"


class RotationDays(str, Enum):
    monday = "monday"
    tuesday = "tuesday"
    wednesday = "wednesday"
    thursday = "thursday"
    friday = "friday"
    saturday = "saturday"
    sunday = "sunday"


class OnCallDays(str, Enum):
    monday = "monday"
    tuesday = "tuesday"
    wednesday = "wednesday"
    thursday = "thursday"
    friday = "friday"
    saturday = "saturday"
    sunday = "sunday"


class VisitType(str, Enum):
    WoundCare = "Wound Care Visit"
    Acute = "Acute Visit"
    Medicare = "Medicare Compliance Visit"
    FollowUp = "Follow-up Visit"
    Routine = "Routine Check"


class BillingLocationCode(str, Enum):
    POS31 = "POS 31 - Skilled Nursing Facility"
    POS32 = "POS 32 - Nursing Facility"
    POS61 = "POS 61 - Comprehensive Inpatient Rehab"
    POS13 = "POS 13 - Assisted Living Facility"


# ========================= API ========================= #



def _s3_client():
    region = settings.AWS_REGION
    kwargs = {
        "region_name": region,
        "config": Config(signature_version="s3v4"),
    }
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    return boto3.client("s3", **kwargs)



def _get_bucket_name():
    b = settings.AWS_S3_BUCKET
    if not b:
        raise HTTPException(status_code=500, detail="AWS_S3_BUCKET env not set")
    return b




def _put_object(s3, bucket: str, key: str, data: bytes, content_type: str | None):
    """
    Uploads a file to S3 with optional KMS encryption.
    """
    extra = {}

    # Use KMS key if set
    if settings.KMS_KEY_ARN:
        extra["ServerSideEncryption"] = "aws:kms"
        extra["SSEKMSKeyId"] = settings.KMS_KEY_ARN

    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
            **extra,
        )
    except s3.exceptions.ClientError as e:
        raise HTTPException(status_code=500, detail=f"S3 upload failed: {str(e)}")


@router.post("/create/")
async def create_provider(
    request: Request,

    # 🔹 Basic
    email: EmailStr = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),

    first_name: str = Form(None),
    middle_name: str = Form(None),
    last_name: str = Form(None),

    degree_enum: DegreeEnum = Form(None),
    speciality: Speciality = Form(None),
    subspeciality: str = Form(None),

    npi_no: str = Form(None),
    taxonomy_code: str = Form(None),
    license_no: str = Form(None),
    license_state: str = Form(None),
    dea_no: str = Form(None),
    dea_expiration_date: str = Form(None),

    professional_email: EmailStr = Form(None),
    professional_phone: str = Form(None),

    # 🔹 Facilities
    facility_ids: str = Form(...),
    primary_facility_id: str = Form(...),

    # 🔹 Enums
    
    rotation_days: List[RotationDays] = Form(...),
    oncall_days: List[OnCallDays] = Form(...),
    visit_type: VisitType = Form(...),
    billing_location_code: BillingLocationCode = Form(...),

    # 🔹 Files
    profile_pic: UploadFile = File(None),
    signature: UploadFile = File(None),

    # 🔹 Auth
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # ================== AUTH USER ================== #
        creator = await UserDoc.get(current_user_id)
        if not creator:
            raise HTTPException(404, "Creator user not found")

        # ================== ENCRYPTION ================== #
        ce = getattr(request.app, "client_encryption", None)
        if not ce:
            ce = init_encryption()
            request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None)
        if not dek_id:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        # ================== FACILITY IDS ================== #
        try:
            facility_object_ids = [
                ObjectId(fid.strip()) for fid in facility_ids.split(",")
            ]
        except Exception:
            raise HTTPException(400, "Invalid facility_ids format")

        if primary_facility_id not in [str(x) for x in facility_object_ids]:
            raise HTTPException(400, "Primary facility must be in facility_ids")

        facilities = []
        for fid in facility_object_ids:
            f = await Facility.get(fid)
            if f:
                facilities.append(f)

        if len(facilities) != len(facility_object_ids):
            raise HTTPException(400, "Invalid or unauthorized facility")

        primary_facility = next(
            (f for f in facilities if str(f.id) == primary_facility_id), None
        )
        if not primary_facility:
            raise HTTPException(400, "Primary facility not found")

        # ================== USER ================== #
        enc_email_det = encrypt_value_deterministic(ce, dek_id, email)
        if await UserDoc.find_one(UserDoc.email == enc_email_det):
            raise HTTPException(400, "Email already exists")

        
        user = UserDoc(
            full_name=encrypt_value(ce, dek_id, full_name),
            email=enc_email_det,
            password=encrypt_value(ce, dek_id, hash_password(password)),
            role=encrypt_value(ce, dek_id, UserRole.PROVIDER.value),
            full_name_search = full_name,
            email_search = email,
            phone_search = professional_phone,
            is_active=True,
            created_by=creator,
        )
        await user.insert()

        # ================== FILE UPLOAD ================== #
        # def upload(file: UploadFile, folder: str):
        #     try:
        #         name = safe_filename(file.filename)
        #         key = f"providers/{user.id}/{folder}/{name}"
        #         put_object(file.file, key)
        #         return f"https://{get_bucket_name()}.s3.amazonaws.com/{key}"
        #     except Exception as e:
        #         print("eeeeeeeeeeee",e)
        #         raise HTTPException(500, f"Failed to upload {folder}")

        def upload(file: UploadFile, folder: str):
            try:
                s3 = _s3_client()
                bucket = _get_bucket_name()

                name = safe_filename(file.filename)
                key = f"providers/{user.id}/{folder}/{name}"

                data = file.file.read()  # 👈 bytes
                if not data:
                    raise HTTPException(400, "Empty file")

                _put_object(
                    s3=s3,
                    bucket=bucket,
                    key=key,
                    data=data,
                    content_type=file.content_type,
                )

                return f"https://{bucket}.s3.amazonaws.com/{key}"

            except Exception as e:
                print("❌ S3 UPLOAD ERROR:", e)
                raise HTTPException(500, f"Failed to upload {folder}")


        profile_pic_url = upload(profile_pic, "profile") if profile_pic else None
        signature_url = upload(signature, "signature") if signature else None

        # ================== ENCRYPT PROVIDER DATA ================== #
        encrypted_provider_data = encrypt_dict(
            ce,
            dek_id,
            {
                "first_name": first_name,
                "middle_name": middle_name,
                "last_name": last_name,
                "degree": degree_enum.value if degree_enum else None,
                "speciality": speciality.value if speciality else None,
                "subspeciality": subspeciality,
                "npi_no": npi_no,
                "taxonomy_code": taxonomy_code,
                "license_no": license_no,
                "license_state": license_state,
                "dea_no": dea_no,
                "dea_expiration_date": dea_expiration_date,
                "professional_email": professional_email,
                "professional_phone": professional_phone,
                "rotation_days": [d.value for d in rotation_days],
                "oncall_days": [d.value for d in oncall_days],
                "visit_type": visit_type.value,
                "billing_location_code": billing_location_code.value,
            },
        )

        # ================== PROVIDER ================== #
        provider = Provider(
            **encrypted_provider_data,
            created_by=creator,
            user=user,
            facility_ids=facilities,
            primary_facility_id=primary_facility,
            profile_pic=profile_pic_url,
            signature=signature_url,
        )
        await provider.insert()

        return {
            "success": True,
            "provider_id": str(provider.id),
            "user_id": str(user.id),
        }

    except HTTPException:
        # 🔹 Known / expected errors
        raise

    except Exception as e:
        # 🔥 Unexpected crash
        print("❌ CREATE PROVIDER CRASH:", str(e))
        raise HTTPException(
            status_code=500,
            detail="Internal server error while creating provider",
        )


# ========================= LIST PROVIDERS ========================= #

@router.get("/list/")
async def get_all_providers(
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
            Provider.is_deleted == False
        ]

        # Decrypt user role for comparison
        user_role_decrypted = decrypt_value(ce, user.role) if user.role else None

        # Check user role and apply conditions accordingly
        if user_role_decrypted == UserRole.ADMIN:
            conditions.append(Provider.created_by.id == user.id)
        elif user_role_decrypted == UserRole.SCHEDULER:
            scheduler_record = await Scheduler.find_one(
                Scheduler.user.id == user.id, fetch_links=True
            )
            if scheduler_record and scheduler_record.created_by:
                admin_id = scheduler_record.created_by.id
                conditions.append(Provider.created_by.id == admin_id)
            else:
                # If scheduler has no creator, or no scheduler record, they see no providers.
                # Add a condition that will never be met.
                conditions.append(Provider.id == PydanticObjectId("000000000000000000000000"))

        if status:
            conditions.append(Provider.status == status.lower())

        # Note: Search is limited for encrypted fields unless we implement searchable encryption
        # For now we can search by non-encrypted fields or handle filtering in memory (not efficient for large data)
        # Assuming status and created_at are not encrypted


        if search:
            search_value = search.lower()
            conditions.append(
                Or(
                    RegEx(Provider.user.full_name_search, f"^{search_value}"),
                    RegEx(Provider.user.phone_search, f"^{search_value}"),
                    RegEx(Provider.user.email_search, f"^{search_value}"),
                    RegEx(Provider.facility_ids.facility_name_search, f"^{search_value}"),
                   
                )
               
            )
        
        

        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------
        providers = await (
            Provider.find(
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
        total = await Provider.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------
        result = []
        for prov in providers:
            # Safely get facility info
            facility_list = []
            if prov.facility_ids:
                for fac in prov.facility_ids:
                    if fac: # check if link resolved
                        facility_list.append({
                            "id": str(fac.id),
                            "name": fac.facility_name_search
                        })
            
            primary_fac_data = None
            if prov.primary_facility_id:
                primary_fac_data = {
                    "id": str(prov.primary_facility_id.id),
                    "name": prov.primary_facility_id.facility_name_search
                }

            # rotation_days and oncall_days may be stored as encrypted list or string
            rd_raw = decrypt_value(ce, prov.rotation_days)
            oc_raw = decrypt_value(ce, prov.oncall_days)
            rotation_days = (
                rd_raw if isinstance(rd_raw, list)
                else ([rd_raw] if rd_raw else [])
            )
            oncall_days = (
                oc_raw if isinstance(oc_raw, list)
                else ([oc_raw] if oc_raw else [])
            )

            result.append({
                "id": str(prov.id),
                "full_name": decrypt_value(ce, prov.user.full_name) if prov.user else None,
                "email": decrypt_value(ce, prov.user.email) if prov.user else None,
                "first_name": decrypt_value(ce, prov.first_name),
                "middle_name" : decrypt_value(ce, prov.middle_name),
                "last_name": decrypt_value(ce, prov.last_name),
                # "phone": decrypt_value(ce, prov.user.phone),
                "degree": decrypt_value(ce, prov.degree),
                "speciality": decrypt_value(ce, prov.speciality),
                "subspeciality": decrypt_value(ce, prov.subspeciality),
                "npi_no": decrypt_value(ce, prov.npi_no),
                "taxonomy_code": decrypt_value(ce, prov.taxonomy_code),
                "license_no": decrypt_value(ce, prov.license_no),
                "license_state": decrypt_value(ce, prov.license_state),
                "dea_no": decrypt_value(ce, prov.dea_no),
                "dea_expiration_date": decrypt_value(ce, prov.dea_expiration_date),
                "professional_phone": decrypt_value(ce, prov.professional_phone),
                "visit_type" : decrypt_value(ce, prov.visit_type),
                "location_code" : decrypt_value(ce, prov.billing_location_code),
                "rotation_days": rotation_days,
                "oncall_days": oncall_days,
                "profile_pic": prov.profile_pic,
                "profile_pic": prov.signature,
                "facilities": facility_list,
                "primary_facility": primary_fac_data,
               
                "status": prov.status,
                "created_at": prov.created_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Provider",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Providers fetched | "
                    f"page={page}, page_size={page_size}, "
                    f"status={status}, "
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


# ========================= UPDATE PROVIDER ========================= #

@router.put("/update/{provider_id}")
async def update_provider(
    provider_id: str,
    request: Request,

    # 🔹 Basic
    first_name: str = Form(None),
    middle_name: str = Form(None),
    last_name: str = Form(None),
    full_name: str = Form(None),

    degree_enum: DegreeEnum = Form(None),
    speciality: Speciality = Form(None),
    subspeciality: str = Form(None),

    npi_no: str = Form(None),
    taxonomy_code: str = Form(None),
    license_no: str = Form(None),
    license_state: str = Form(None),
    dea_no: str = Form(None),
    dea_expiration_date: str = Form(None),

    professional_email: EmailStr = Form(None),
    professional_phone: str = Form(None),

    # 🔹 Facilities
    facility_ids: str = Form(None),
    primary_facility_id: str = Form(None),

    # 🔹 Enums
    rotation_days: List[RotationDays] = Form(None),
    oncall_days: List[OnCallDays] = Form(None),
    visit_type: VisitType = Form(None),
    billing_location_code: BillingLocationCode = Form(None),

    # 🔹 Files
    profile_pic: UploadFile = File(None),
    signature: UploadFile = File(None),
    
    status: str = Form(None),

    # 🔹 Auth
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # 1️⃣ User & Provider
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(404, "User not found")
            
        provider = await Provider.get(provider_id, fetch_links=True)
        if not provider:
            raise HTTPException(404, "Provider not found")

        # 2️⃣ Encryption
        ce = getattr(request.app, "client_encryption", None)
        # Check if ce is None OR if it's not a valid object (e.g. somehow became a string)
        # We assume ClientEncryption is not a string.
        if not ce or isinstance(ce, str):
            print("⚠️ Re-initializing ClientEncryption in Update Provider")
            ce = init_encryption()
            request.app.client_encryption = ce
            
        dek_id = getattr(request.app, "dek_id", None)
        if not dek_id:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        # 3️⃣ Update Facilities if provided
        if facility_ids:
            try:
                # Handle spaces after commas and filter out empty strings
                facility_object_ids = [
                    ObjectId(fid.strip()) for fid in facility_ids.split(",") if fid.strip()
                ]
            except Exception:
                raise HTTPException(400, "Invalid facility_ids format")
            
            facilities = []
            for fid in facility_object_ids:
                f = await Facility.get(fid)
                if f:
                    facilities.append(f)
            
            if len(facilities) != len(facility_object_ids):
                raise HTTPException(400, "Invalid or unauthorized facility")
                
            provider.facility_ids = facilities
        
        if primary_facility_id:
            # If facilities updated, check in new list, else check in existing
            current_fac_ids = [str(f.id) for f in provider.facility_ids] if provider.facility_ids else []
            
            if primary_facility_id not in current_fac_ids:
                 raise HTTPException(400, "Primary facility must be in facility_ids")
                 
            provider.primary_facility_id = await Facility.get(primary_facility_id)

        # 4️⃣ Update Encrypted Fields
        update_data = {}
        
        if first_name is not None: update_data["first_name"] = first_name
        if middle_name is not None: update_data["middle_name"] = middle_name
        if last_name is not None: update_data["last_name"] = last_name
        
        if degree_enum is not None: update_data["degree"] = degree_enum.value
        if speciality is not None: update_data["speciality"] = speciality.value
        if subspeciality is not None: update_data["subspeciality"] = subspeciality
        
        if npi_no is not None: update_data["npi_no"] = npi_no
        if taxonomy_code is not None: update_data["taxonomy_code"] = taxonomy_code
        if license_no is not None: update_data["license_no"] = license_no
        if license_state is not None: update_data["license_state"] = license_state
        if dea_no is not None: update_data["dea_no"] = dea_no
        if dea_expiration_date is not None: update_data["dea_expiration_date"] = dea_expiration_date
        
        if professional_email is not None: update_data["professional_email"] = professional_email
        if professional_phone is not None: update_data["professional_phone"] = professional_phone
        
        if rotation_days is not None: update_data["rotation_days"] = [d.value for d in rotation_days]
        if oncall_days is not None: update_data["oncall_days"] = [d.value for d in oncall_days]
        if visit_type is not None: update_data["visit_type"] = visit_type.value
        if billing_location_code is not None: update_data["billing_location_code"] = billing_location_code.value

        if update_data:
            encrypted_data = encrypt_dict(ce, dek_id, update_data)
            for k, v in encrypted_data.items():
                setattr(provider, k, v)

        # 5️⃣ Update Files
        def upload(file: UploadFile, folder: str):
            try:
                s3 = _s3_client()
                bucket = _get_bucket_name()
                name = safe_filename(file.filename)
                # Use provider's user id for path consistency
                user_id = provider.user.id if provider.user else provider.id 
                key = f"providers/{user_id}/{folder}/{name}"
                data = file.file.read()
                if not data: return None
                _put_object(s3=s3, bucket=bucket, key=key, data=data, content_type=file.content_type)
                return f"https://{bucket}.s3.amazonaws.com/{key}"
            except Exception as e:
                print("❌ S3 UPLOAD ERROR:", e)
                return None

        if profile_pic:
            url = upload(profile_pic, "profile")
            if url: provider.profile_pic = url
            
        if signature:
            url = upload(signature, "signature")
            if url: provider.signature = url

        # 6️⃣ Status Update
        if status:
            provider.status = status

        # 7️⃣ User Full Name Update (if linked)
        if full_name and provider.user:
            linked_user = await UserDoc.get(provider.user.id)
            if linked_user:
                linked_user.full_name = encrypt_value(ce, dek_id, full_name)
                linked_user.full_name_search = full_name
                linked_user.email_search = professional_email
                linked_user.phone_search = professional_phone
                linked_user.updated_at = datetime.now(timezone.utc)
                await linked_user.save()

        provider.updated_at = datetime.now(timezone.utc)
        await provider.save()

        # 8️⃣ Audit
        await log_audit(
            user_id=str(current_user_id),
            request=request,
            action="Update",
            resource="Provider",
            resource_id=str(provider.id),
            status="success",
            notes=f"Provider updated: {provider.id}",
        )

        return {
            "success": True,
            "provider_id": str(provider.id),
            "message": "Provider updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ UPDATE PROVIDER CRASH: {e} | Type: {type(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

# ========================= PROVIDER-WISE SCHEDULES ========================= #



@router.get("/schedules/my")
async def get_my_provider_schedules(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None, description="Filter by start date for appointments"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date for appointments"),
    facility_id: Optional[str] = Query(None, description="Filter schedules by facility ID"),
):
    try:
        # 1️⃣ Logged-in user
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 2️⃣ Provider by token user
        provider = await Provider.find_one(
            Provider.user.id == user.id,
            Provider.is_deleted == False,
            fetch_links=True,
        )

        if not provider:
            raise HTTPException(
                status_code=403,
                detail="Only provider users can access schedules"
            )

        # 3️⃣ Encryption init
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        # 4️⃣ Build schedule query
        conditions = [
            ScheduleDoc.provider_id.id == provider.id,
            ScheduleDoc.is_deleted == False,
        ]

        if status:
            conditions.append(ScheduleDoc.status == status.lower())

        if facility_id:
            conditions.append(ScheduleDoc.facility_id.id == PydanticObjectId(facility_id))

        if start_date and end_date:
            conditions.append(ScheduleDoc.appointment_datetime >= start_date)
            conditions.append(ScheduleDoc.appointment_datetime <= end_date)
        elif start_date:
            conditions.append(ScheduleDoc.appointment_datetime >= start_date)
        elif end_date:
            conditions.append(ScheduleDoc.appointment_datetime <= end_date)

        if search:
            search_value = search.lower().strip()
            conditions.append(
                Or(
                    RegEx(
                        ScheduleDoc.patient_id.user_id.full_name_search,
                        f"^{search_value}",
                        options="i"
                    ),
                    RegEx(
                        ScheduleDoc.facility_id.facility_name_search,
                        f"^{search_value}",
                        options="i"
                    ),
                )
            )

        query = ScheduleDoc.find(*conditions, fetch_links=True).sort("-appointment_datetime")

        total = await query.count()
        schedules = (
            await query
            .skip((page - 1) * page_size)
            .limit(page_size)
            .to_list()
        )

        # 5️⃣ Response
        grouped_data = {}
        for sch in schedules:
            facility_info = None
            fac_id = "unknown"
            if sch.facility_id:
                fac = sch.facility_id
                if hasattr(fac, "fetch") and not hasattr(fac, "facility_name_search"):
                    fac = await fac.fetch()
                
                if fac:
                    fac_id = str(fac.id)
                    facility_info = {
                        "id": fac_id,
                        "facility_name_search": getattr(fac, "facility_name_search", None),
                        "status": fac.status,
                    }

            if fac_id not in grouped_data:
                grouped_data[fac_id] = {
                    "facility": facility_info,
                    "schedules": []
                }

            patient_details = {}
            if sch.patient_id:
                patient = sch.patient_id
                if hasattr(patient, "fetch") and not hasattr(patient, "personal_information"):
                    patient = await patient.fetch()
                
                if patient:
                    if hasattr(patient, "personal_information") and hasattr(patient, "user_id"):
                        pat_user = getattr(patient, "user_id", None)
                        if pat_user and hasattr(pat_user, "fetch") and not hasattr(pat_user, "full_name_search"):
                            await patient.fetch_link("user_id")

                    pat_name = None
                    pat_user = getattr(patient, "user_id", None)
                    if pat_user and hasattr(pat_user, "fetch") and not hasattr(pat_user, "full_name_search"):
                        pat_user = await pat_user.fetch()

                    if pat_user:
                        pat_name = getattr(pat_user, "full_name_search", None)
                
                if not pat_name and patient.personal_information:
                    pi = json.loads(decrypt_value(ce, patient.personal_information) or '{}')
                    fn = (pi.get("first_name") or "").strip()
                    ln = (pi.get("last_name") or "").strip()
                    pat_name = f"{fn} {ln}".strip()

                bed_details = {}
                room_details = {}
                if patient.bed_id:
                    bed_id_val = patient.bed_id.id if hasattr(patient.bed_id, "id") else patient.bed_id.ref.id
                    bed = await Beds.get(bed_id_val, fetch_links=True)
                    if bed:
                        bed_details = {
                            "id": str(bed.id),
                            "bed_number": decrypt_value(ce, bed.bed_number),
                            "status": decrypt_value(ce, bed.bed_status),
                        }
                        if bed.room_id:
                            room_id_val = bed.room_id.id if hasattr(bed.room_id, "id") else bed.room_id.ref.id
                            room = await FacilityRooms.get(room_id_val)
                            if room:
                                room_details = {
                                    "id": str(room.id),
                                    "room_number": decrypt_value(ce, room.room_number),
                                    "room_type": decrypt_value(ce, room.room_type),
                                }

                patient_details = {
                    "id": str(patient.id),
                    "name": pat_name,
                    "email": getattr(pat_user, "email_search", None) if pat_user else None,
                    "phone": getattr(pat_user, "phone_search", None) if pat_user else None,
                    "bed": bed_details,
                    "room": room_details,
                }

            grouped_data[fac_id]["schedules"].append({
                "id": str(sch.id),
                "provider": {"id": str(provider.id)},
                "visit_type": {
                    "id": str(sch.visit_type.id),
                    "name": sch.visit_type.name
                } if sch.visit_type else None,
                "appointment_datetime": sch.appointment_datetime.isoformat() if sch.appointment_datetime else None,
                "status": sch.status,
                "notes": sch.notes,
                "patient": patient_details,
                "created_at": sch.created_at,
                "updated_at": sch.updated_at,
            })

        result = list(grouped_data.values())

        return {
            "success": True,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "total_schedules": total,
            "count": len(schedules),
            "data": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ PROVIDER SCHEDULES CRASH:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")


# =========================================
# Providers with Facilities and Patients
# =========================================
@router.get("/with-facilities-patients/")
async def providers_with_facilities_patients(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    facility_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="Filter providers by status"),
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if not ce:
            ce = init_encryption()
            request.app.client_encryption = ce

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        conditions = [Provider.is_deleted == False]
        if status:
            conditions.append(Provider.status == status.lower())

        providers = await Provider.find(*conditions, fetch_links=True).to_list()

        result = []
        for prov in providers:
            try:
                first = decrypt_value(ce, prov.first_name).strip('"') if prov.first_name else ""
            except Exception:
                first = ""
            try:
                last = decrypt_value(ce, prov.last_name).strip('"') if prov.last_name else ""
            except Exception:
                last = ""
            provider_name = f"{first} {last}".strip() or (
                getattr(getattr(prov, "user", None), "full_name_search", None) or None
            )

            facilities = []
            fac_links = (prov.facility_ids or [])
            if prov.primary_facility_id and prov.primary_facility_id not in fac_links:
                fac_links = [prov.primary_facility_id] + fac_links

            for fac in fac_links:
                if facility_id and str(fac.id) != facility_id:
                    continue
                try:
                    patients = await PatientDoc.find(
                        PatientDoc.facility_id.id == fac.id,
                        PatientDoc.is_deleted == False,
                        fetch_links=True
                    ).to_list()
                except Exception:
                    patients = []

                patients_list = []
                for p in patients:
                    # Patient display name
                    p_name = None
                    if p.user_id:
                        p_name = getattr(p.user_id, "full_name_search", None)
                        if not p_name and getattr(p.user_id, "full_name", None):
                            try:
                                p_name = decrypt_value(ce, p.user_id.full_name).strip('"')
                            except Exception:
                                p_name = None

                    if not p_name and p.personal_information:
                        try:
                            pi = decrypt_value(ce, p.personal_information)
                            try:
                                pi_obj = json.loads(pi) if isinstance(pi, str) else pi
                            except Exception:
                                pi_obj = {}
                            fn = (pi_obj.get("first_name") or "").strip()
                            ln = (pi_obj.get("last_name") or "").strip()
                            p_name = f"{fn} {ln}".strip() if (fn or ln) else None
                        except Exception:
                            p_name = None

                    # Contact
                    user_email = None
                    user_phone = None
                    if p.user_id:
                        user_email = getattr(p.user_id, "email_search", None)
                        if not user_email and getattr(p.user_id, "email", None):
                            try:
                                user_email = decrypt_value(ce, p.user_id.email).strip('"')
                            except Exception:
                                user_email = None
                        user_phone = getattr(p.user_id, "phone_search", None)
                        if not user_phone and getattr(p.user_id, "phone", None):
                            try:
                                user_phone = decrypt_value(ce, p.user_id.phone).strip('"')
                            except Exception:
                                user_phone = None

                    # Assigned provider name (if any)
                    assigned_provider_name = None
                    if p.provider_id:
                        try:
                            pf = decrypt_value(ce, p.provider_id.first_name).strip('"') if p.provider_id.first_name else ""
                            pl = decrypt_value(ce, p.provider_id.last_name).strip('"') if p.provider_id.last_name else ""
                            assigned_provider_name = f"{pf} {pl}".strip()
                        except Exception:
                            assigned_provider_name = None

                    # Safe JSON decrypt helper
                    def _dec_json(binval):
                        try:
                            if not binval:
                                return None
                            s = decrypt_value(ce, binval)
                            try:
                                return json.loads(s) if isinstance(s, str) else s
                            except Exception:
                                return s
                        except Exception:
                            return None

                    patients_list.append({
                        "id": str(p.id),
                        "name": p_name,
                        "user_email": user_email,
                        "user_phone": user_phone,
                        "provider_id": (str(p.provider_id.id) if p.provider_id else None),
                        "provider_name": assigned_provider_name,
                        "facility_id": str(fac.id),
                        "personal_information": _dec_json(p.personal_information),
                        "admission_information": _dec_json(p.admisson_information),
                        "address_information": _dec_json(p.address_information),
                        "insurance_information": _dec_json(p.insurance_information),
                        "diagnosis_information": _dec_json(p.diagnosis),
                        "created_at": p.created_at,
                        "updated_at": p.updated_at,
                    })

                facilities.append({
                    "id": str(fac.id),
                    "name": getattr(fac, "facility_name_search", None),
                    "status": getattr(fac, "status", None),
                    "patients_count": len(patients_list),
                    "patients": patients_list,
                })

            result.append({
                "provider": {
                    "id": str(prov.id),
                    "name": provider_name,
                    "status": prov.status,
                    "user_full_name": getattr(getattr(prov, "user", None), "full_name_search", None)
                },
                "facilities": facilities,
            })

        return {
            "success": True,
            "count": len(result),
            "data": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        print("❌ PROVIDERS WITH FACILITIES & PATIENTS CRASH:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")




# ----------------------------------------- Provider id wise show all data and facility and patient 


@router.get("/{provider_id}/")
async def single_providers_with_facilities_patients(
    request: Request,
    provider_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        try:
            prov_oid = ObjectId(provider_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid provider_id")

        provider = await Provider.get(prov_oid, fetch_links=True)
        if not provider or provider.is_deleted:
            raise HTTPException(status_code=404, detail="Provider not found")

        # Initialize encryption early for role check
        ce = getattr(request.app, "client_encryption", None)
        if not ce or isinstance(ce, str):
            ce = init_encryption()
            request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None)
        if not dek_id:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        # Decrypt user role for comparison
        user_role_decrypted = decrypt_value(ce, user.role) if user.role else None

        # --- Role-based access check ---
        is_allowed = False
        if provider.created_by:  # Provider must have a creator
            if user_role_decrypted == UserRole.ADMIN:
                # Admin can see providers they created
                if provider.created_by.id == user.id:
                    is_allowed = True
            elif user_role_decrypted == UserRole.SCHEDULER:
                # Scheduler can see providers created by the SAME admin who created them
                scheduler_record = await Scheduler.find_one(
                    Scheduler.user.id == user.id, fetch_links=True
                )
                if scheduler_record and scheduler_record.created_by:
                    if provider.created_by.id == scheduler_record.created_by.id:
                        is_allowed = True
        
        if not is_allowed:
            raise HTTPException(
                status_code=403, detail="Not allowed to view this provider"
            )


        try:
            first = decrypt_value(ce, provider.first_name).strip('"') if provider.first_name else ""
        except Exception:
            first = ""
        try:
            last = decrypt_value(ce, provider.last_name).strip('"') if provider.last_name else ""
        except Exception:
            last = ""

        provider_name = f"{first} {last}".strip() or (
            getattr(getattr(provider, "user", None), "full_name_search", None) or None
        )

        facilities = []
        fac_links = provider.facility_ids or []
        if provider.primary_facility_id and provider.primary_facility_id not in fac_links:
            fac_links = [provider.primary_facility_id] + fac_links

        def _dec_json(binval):
            try:
                if not binval:
                    return None
                s = decrypt_value(ce, binval)
                try:
                    return json.loads(s) if isinstance(s, str) else s
                except Exception:
                    return s
            except Exception:
                return None

        # Har facility ke andar us facility ke jitne patients hain (regardless of provider)
        for fac in fac_links:
            try:
                patients = await PatientDoc.find(
                    PatientDoc.facility_id.id == fac.id,
                    PatientDoc.is_deleted == False,
                    fetch_links=True,
                ).to_list()
            except Exception:
                patients = []

            patients_list = []
            for p in patients:
                p_name = None
                if p.user_id:
                    p_name = getattr(p.user_id, "full_name_search", None)
                    if not p_name and getattr(p.user_id, "full_name", None):
                        try:
                            p_name = decrypt_value(ce, p.user_id.full_name).strip('"')
                        except Exception:
                            p_name = None


                if not p_name and p.personal_information:
                    try:
                        pi = decrypt_value(ce, p.personal_information)
                        try:
                            pi_obj = json.loads(pi) if isinstance(pi, str) else pi
                        except Exception:
                            pi_obj = {}
                        fn = (pi_obj.get("first_name") or "").strip()
                        ln = (pi_obj.get("last_name") or "").strip()
                        p_name = f"{fn} {ln}".strip() if (fn or ln) else None
                    except Exception:
                        p_name = None

                user_email = None
                user_phone = None
                if p.user_id:
                    user_email = getattr(p.user_id, "email_search", None)
                    if not user_email and getattr(p.user_id, "email", None):
                        try:
                            user_email = decrypt_value(ce, p.user_id.email).strip('"')
                        except Exception:
                            user_email = None
                    user_phone = getattr(p.user_id, "phone_search", None)
                    if not user_phone and getattr(p.user_id, "phone", None):
                        try:
                            user_phone = decrypt_value(ce, p.user_id.phone).strip('"')
                        except Exception:
                            user_phone = None

                assigned_provider_name = None
                if p.provider_id:
                    try:
                        pf = decrypt_value(ce, p.provider_id.first_name).strip('"') if p.provider_id.first_name else ""
                        pl = decrypt_value(ce, p.provider_id.last_name).strip('"') if p.provider_id.last_name else ""
                        assigned_provider_name = f"{pf} {pl}".strip()
                    except Exception:
                        assigned_provider_name = None

                patients_list.append(
                    {
                        "id": str(p.id),
                        "name": p_name,
                        "user_email": user_email,
                        "user_phone": user_phone,
                        "provider_id": str(p.provider_id.id) if p.provider_id else None,
                        "provider_name": assigned_provider_name,
                        "facility_id": str(fac.id),
                        "personal_information": _dec_json(p.personal_information),
                        "admission_information": _dec_json(p.admisson_information),
                        "address_information": _dec_json(p.address_information),
                        "insurance_information": _dec_json(p.insurance_information),
                        "diagnosis_information": _dec_json(p.diagnosis),
                        "created_at": p.created_at,
                        "updated_at": p.updated_at,
                    }
                )

            facilities.append(
                {
                    "id": str(fac.id),
                    "name": getattr(fac, "facility_name_search", None),
                    "status": getattr(fac, "status", None),
                    "patients_count": len(patients_list),
                    "patients": patients_list,
                }
            )

        return {
            "success": True,
            "provider": {
                "id": str(provider.id),
                "name": provider_name,
                "status": provider.status,
                "user_full_name": getattr(getattr(provider, "user", None), "full_name_search", None),
            },
            "facilities": facilities,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ PROVIDER SINGLE WITH FACILITIES & PATIENTS CRASH: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# @router.get("/all/scheduled/")
# async def list_all_scheduled_providers(
#     request: Request,
#     page: int = Query(1, ge=1),
#     page_size: int = Query(10, ge=1, le=100),
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     """
#     Returns a list of all providers who have active schedules, 
#     grouped by Provider -> Facility -> Patients. (Paginated by Provider)
#     """
#     try:
#         # 👤 User Validation
#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         # 🔐 Encryption Init
#         ce = getattr(request.app, "client_encryption", None)
#         if not ce or isinstance(ce, str):
#             ce = init_encryption()
#             request.app.client_encryption = ce

#         # 📅 1️⃣ Find unique Provider IDs with active schedules
#         # Beanie aggregate to get distinct provider IDs
#         pipeline_total = [
#             {
#                 "$match": {
#                     "is_deleted": False, 
#                     "status": {"$in": ["scheduled", "rescheduled"]},
#                     "provider_id": {"$ne": None}
#                 }
#             },
#             {"$group": {"_id": "$provider_id.$id"}}
#         ]
#         all_unique_providers = await ScheduleDoc.aggregate(pipeline_total).to_list()
#         # Ensure we have clean ObjectIds from the aggregation
#         paginated_provider_ids_all = []
#         for r in all_unique_providers:
#             if r.get("_id"):
#                 try:
#                     paginated_provider_ids_all.append(ObjectId(str(r["_id"])))
#                 except:
#                     continue
        
#         total_providers = len(paginated_provider_ids_all)

#         # 2️⃣ Paginate those Provider IDs
#         skip = (page - 1) * page_size
#         paginated_provider_ids = paginated_provider_ids_all[skip : skip + page_size]

#         if not paginated_provider_ids:
#             return {
#                 "success": True,
#                 "page": page,
#                 "page_size": page_size,
#                 "total": total_providers,
#                 "data": []
#             }

#         # 3️⃣ Fetch ALL active schedules for these paginated providers
#         # Use explicit In operator with ObjectIds for maximum compatibility
#         all_schedules = await ScheduleDoc.find(
#             In(ScheduleDoc.provider_id.id, paginated_provider_ids),
#             ScheduleDoc.is_deleted == False,
#             In(ScheduleDoc.status, ["scheduled", "rescheduled"]),
#             fetch_links=True
#         ).to_list()

#         # Sort manually if needed to avoid potential link sorting issues on server
#         all_schedules.sort(key=lambda x: x.appointment_datetime if x.appointment_datetime else datetime.min)

#         print(f"🔍 DEBUG SERVER: total_providers={total_providers}, paginated_count={len(paginated_provider_ids)}, schedules_found={len(all_schedules)}")

#         def safe_dec(val):
#             try:
#                 return decrypt_value(ce, val).strip('"') if val else ""
#             except:
#                 return ""

#         def dec_json(val):
#             try:
#                 if not val:
#                     return None
#                 s = decrypt_value(ce, val)
#                 return json.loads(s) if isinstance(s, str) else s
#             except:
#                 return None

#         async def resolve_doc(link_or_doc, required_attr: Optional[str] = None):
#             if not link_or_doc:
#                 return None
#             resolved = link_or_doc
#             try:
#                 if isinstance(resolved, Link):
#                     resolved = await resolved.fetch()
#                 elif required_attr and hasattr(resolved, "fetch") and not hasattr(resolved, required_attr):
#                     resolved = await resolved.fetch()
#             except Exception:
#                 return None
#             return resolved

#         def extract_id(doc_or_link):
#             if not doc_or_link:
#                 return None
#             if hasattr(doc_or_link, "id") and getattr(doc_or_link, "id", None):
#                 return doc_or_link.id
#             ref = getattr(doc_or_link, "ref", None)
#             if ref is not None and hasattr(ref, "id"):
#                 return ref.id
#             return None

#         # 🏗️ Nested Grouping: Provider -> Facility
#         provider_groups = {}

#         for sch in all_schedules:
#             prov = await resolve_doc(sch.provider_id, "first_name")
#             fac = await resolve_doc(sch.facility_id, "facility_name_search")
#             patient = await resolve_doc(sch.patient_id, "personal_information")

#             # Be more lenient: skip only if provider is missing
#             if not prov:
#                 continue

#             prov_id = extract_id(prov)
#             fac_id = extract_id(fac)
#             pat_id = extract_id(patient)
            
#             if not prov_id:
#                 continue

#             prov_id_str = str(prov_id)
#             fac_id_str = str(fac_id) if fac_id else "unknown_facility"

#             # 1️⃣ Ensure Provider entry exists
#             if prov_id_str not in provider_groups:
#                 p_name = f"{safe_dec(prov.first_name)} {safe_dec(prov.last_name)}".strip()
#                 degree = safe_dec(prov.degree)
#                 provider_groups[prov_id_str] = {
#                     "provider_id": prov_id_str,
#                     "provider_name": p_name or "Unknown Provider",
#                     "provider_status": prov.status,
#                     "degree": degree,
#                     "facilities": {} 
#                 }

#             # 2️⃣ Ensure Facility entry exists under this Provider
#             if fac_id_str not in provider_groups[prov_id_str]["facilities"]:
#                 provider_groups[prov_id_str]["facilities"][fac_id_str] = {
#                     "facility_id": fac_id_str,
#                     "facility_name": getattr(fac, "facility_name_search", "Unknown Facility") if fac else "Unknown Facility",
#                     "facility_status": getattr(fac, "status", "unknown") if fac else "unknown",
#                     "appointments": []
#                 }

#             # 3️⃣ Decrypt Patient Name
#             pat_name = "Unknown Patient"
#             pat_user = None
#             if patient:
#                 pat_user = await resolve_doc(getattr(patient, "user_id", None), "full_name_search")
#                 if pat_user:
#                     pat_name = getattr(pat_user, "full_name_search", None)
                
#                 personal_information = getattr(patient, "personal_information", None)
#                 if not pat_name and personal_information:
#                     pi = dec_json(personal_information) or {}
#                     fn = (pi.get("first_name") or "").strip()
#                     ln = (pi.get("last_name") or "").strip()
#                     pat_name = f"{fn} {ln}".strip() or "Unknown Patient"

#             # 4️⃣ Add Appointment to Facility
#             bed_details = {}
#             room_details = {}
#             if patient and getattr(patient, "bed_id", None):
#                 patient_bed = getattr(patient, "bed_id", None)
#                 bed_id_val = extract_id(patient_bed)
#                 bed = await Beds.get(bed_id_val, fetch_links=True) if bed_id_val else None
#                 if bed:
#                     bed_details = {
#                         "id": str(bed.id),
#                         "bed_number": safe_dec(bed.bed_number),
#                         "status": safe_dec(bed.bed_status),
#                     }
#                     if bed.room_id:
#                         room_id_val = extract_id(bed.room_id)
#                         room = await FacilityRooms.get(room_id_val) if room_id_val else None
#                         if room:
#                             room_details = {
#                                 "id": str(room.id),
#                                 "room_number": safe_dec(room.room_number),
#                                 "room_type": safe_dec(room.room_type),
#                             }

#             provider_groups[prov_id_str]["facilities"][fac_id_str]["appointments"].append({
#                 "schedule_id": str(sch.id),
#                 "appointment_datetime": sch.appointment_datetime.isoformat() if sch.appointment_datetime else None,
#                 "status": sch.status,
#                 "notes": sch.notes,
#                 "patient": {
#                     "id": str(pat_id) if pat_id else None,
#                     "name": pat_name,
#                     "email": getattr(pat_user, "email_search", None) if pat_user else None,
#                     "phone": getattr(pat_user, "phone_search", None) if pat_user else None,
#                     "personal_information": dec_json(getattr(patient, "personal_information", None)) if patient else None,
#                     "admission_information": dec_json(getattr(patient, "admisson_information", None)) if patient else None,
#                     "address_information": dec_json(getattr(patient, "address_information", None)) if patient else None,
#                     "insurance_information": dec_json(getattr(patient, "insurance_information", None)) if patient else None,
#                     "diagnosis_information": dec_json(getattr(patient, "diagnosis", None)) if patient else None,
#                     "bed": bed_details,
#                     "room": room_details,
#                 }
#             })

#         # 🔄 Final Response Formatting (Maintain paginated order from IDs)

#         final_data = []
#         for p_id_obj in paginated_provider_ids:
#             p_id_str = str(p_id_obj)
#             if p_id_str in provider_groups:
#                 p_info = provider_groups[p_id_str]
#                 p_info["facilities"] = list(p_info["facilities"].values())
#                 final_data.append(p_info)

        
#         print("TYPE:", type(sch.provider_id))
#         print("VALUE:", sch.provider_id)

#         return {
#             "success": True,
#             "page": page,
#             "page_size": page_size,
#             "total_providers": total_providers,
#             "total_pages": (total_providers + page_size - 1) // page_size,
#             "count": len(final_data),
#             "data": final_data
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         print(f"❌ LIST ALL SCHEDULED PROVIDERS CRASH: {e}")
#         raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/all/scheduled/")
async def list_all_scheduled_providers(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # 👤 User Validation
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 🔐 Encryption Init
        ce = getattr(request.app, "client_encryption", None)
        if not ce or isinstance(ce, str):
            ce = init_encryption()
            request.app.client_encryption = ce

        # 📅 1️⃣ Get unique provider IDs
        pipeline = [
            {
                "$match": {
                    "is_deleted": False,
                    "status": {"$in": ["scheduled", "rescheduled"]},
                    "provider_id": {"$ne": None},
                }
            },
            {"$group": {"_id": "$provider_id.$id"}},
        ]

        result = await ScheduleDoc.aggregate(pipeline).to_list()

        provider_ids_all = []
        for r in result:
            if r.get("_id"):
                try:
                    provider_ids_all.append(ObjectId(str(r["_id"])))
                except:
                    continue

        total_providers = len(provider_ids_all)

        # 📄 Pagination
        skip = (page - 1) * page_size
        paginated_provider_ids = provider_ids_all[skip : skip + page_size]

        if not paginated_provider_ids:
            return {
                "success": True,
                "page": page,
                "page_size": page_size,
                "total_providers": total_providers,
                "data": [],
            }

        # 📅 2️⃣ Fetch schedules
        all_schedules = await ScheduleDoc.find(
            In(ScheduleDoc.provider_id.id, paginated_provider_ids),
            ScheduleDoc.is_deleted == False,
            In(ScheduleDoc.status, ["scheduled", "rescheduled"]),
            fetch_links=True,
        ).to_list()

        all_schedules.sort(
            key=lambda x: x.appointment_datetime if x.appointment_datetime else datetime.min
        )

        print(f"✅ schedules_found={len(all_schedules)}")

        # 🔧 Helpers
        def safe_dec(val):
            try:
                return decrypt_value(ce, val).strip('"') if val else ""
            except:
                return ""

        def dec_json(val):
            try:
                if not val:
                    return None
                s = decrypt_value(ce, val)
                return json.loads(s) if isinstance(s, str) else s
            except:
                return None

        def extract_id(doc):
            if not doc:
                return None

            # Document
            if hasattr(doc, "id") and doc.id:
                return str(doc.id)

            # Link
            if hasattr(doc, "ref") and doc.ref:
                return str(doc.ref.id)

            return None

        async def ensure_doc(doc):
            """अगर Link hai to fetch karo, warna direct return"""
            if not doc:
                return None
            if isinstance(doc, Link):
                try:
                    return await doc.fetch()
                except Exception as e:
                    print("❌ fetch error:", e)
                    return None
            return doc

        # 🏗️ Grouping
        provider_groups = {}

        for sch in all_schedules:
            prov = await ensure_doc(sch.provider_id)
            fac = await ensure_doc(sch.facility_id)
            patient = await ensure_doc(sch.patient_id)

            if not prov:
                continue

            prov_id = extract_id(prov)
            fac_id = extract_id(fac) or "unknown_facility"
            pat_id = extract_id(patient)

            if not prov_id:
                continue

            # 👨‍⚕️ Provider
            if prov_id not in provider_groups:
                provider_groups[prov_id] = {
                    "provider_id": prov_id,
                    "provider_name": f"{safe_dec(prov.first_name)} {safe_dec(prov.last_name)}".strip() or "Unknown Provider",
                    "provider_status": getattr(prov, "status", None),
                    "degree": safe_dec(getattr(prov, "degree", None)),
                    "facilities": {},
                }

            # 🏥 Facility
            if fac_id not in provider_groups[prov_id]["facilities"]:
                provider_groups[prov_id]["facilities"][fac_id] = {
                    "facility_id": fac_id,
                    "facility_name": getattr(fac, "facility_name_search", "Unknown Facility") if fac else "Unknown Facility",
                    "facility_status": getattr(fac, "status", "unknown") if fac else "unknown",
                    "appointments": [],
                }

            # 👤 Patient
            pat_name = "Unknown Patient"
            pat_user = None

            if patient:
                pat_user = await ensure_doc(getattr(patient, "user_id", None))

                if pat_user:
                    pat_name = getattr(pat_user, "full_name_search", None)

                if not pat_name:
                    pi = dec_json(getattr(patient, "personal_information", None)) or {}
                    pat_name = f"{pi.get('first_name','')} {pi.get('last_name','')}".strip() or "Unknown Patient"

            # 🛏️ Bed / Room
            bed_details = {}
            room_details = {}

            if patient and getattr(patient, "bed_id", None):
                bed_link = getattr(patient, "bed_id")
                bed = await ensure_doc(bed_link)

                if bed:
                    bed_details = {
                        "id": str(bed.id),
                        "bed_number": safe_dec(bed.bed_number),
                        "status": safe_dec(bed.bed_status),
                    }

                    if bed.room_id:
                        room = await ensure_doc(bed.room_id)
                        if room:
                            room_details = {
                                "id": str(room.id),
                                "room_number": safe_dec(room.room_number),
                                "room_type": safe_dec(room.room_type),
                            }

            # 📅 Appointment
            provider_groups[prov_id]["facilities"][fac_id]["appointments"].append(
                {
                    "schedule_id": str(sch.id),
                    "appointment_datetime": sch.appointment_datetime.isoformat()
                    if sch.appointment_datetime
                    else None,
                    "status": sch.status,
                    "notes": sch.notes,
                    "patient": {
                        "id": pat_id,
                        "name": pat_name,
                        "email": getattr(pat_user, "email_search", None) if pat_user else None,
                        "phone": getattr(pat_user, "phone_search", None) if pat_user else None,
                        "personal_information": dec_json(getattr(patient, "personal_information", None)) if patient else None,
                        "admission_information": dec_json(getattr(patient, "admisson_information", None)) if patient else None,
                        "address_information": dec_json(getattr(patient, "address_information", None)) if patient else None,
                        "insurance_information": dec_json(getattr(patient, "insurance_information", None)) if patient else None,
                        "diagnosis_information": dec_json(getattr(patient, "diagnosis", None)) if patient else None,
                        "bed": bed_details,
                        "room": room_details,
                    },
                }
            )

        # 🔄 Final Format
        final_data = []
        for p_id in paginated_provider_ids:
            p_id_str = str(p_id)
            if p_id_str in provider_groups:
                p_info = provider_groups[p_id_str]
                p_info["facilities"] = list(p_info["facilities"].values())
                final_data.append(p_info)

        return {
            "success": True,
            "page": page,
            "page_size": page_size,
            "total_providers": total_providers,
            "total_pages": (total_providers + page_size - 1) // page_size,
            "count": len(final_data),
            "data": final_data,
        }

    except Exception as e:
        print("❌ ERROR:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/{provider_id}/scheduled/")
async def provider_scheduled_patients(
    request: Request,
    provider_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    Returns patients scheduled with a specific provider, grouped by facility. (Paginated Appointments)
    """
    try:
        # 👤 User Validation
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 🆔 Provider ID Validation
        try:
            prov_oid = ObjectId(provider_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid provider_id")

        # 🏥 Provider Fetch
        provider = await Provider.get(prov_oid, fetch_links=True)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        
        # 🔐 Encryption Init
        ce = getattr(request.app, "client_encryption", None)
        if not ce or isinstance(ce, str):
            ce = init_encryption()
            request.app.client_encryption = ce

        # 📅 Count total appointments
        total_appointments = await ScheduleDoc.find(
            ScheduleDoc.provider_id.id == prov_oid,
            ScheduleDoc.is_deleted == False,
            In(ScheduleDoc.status, ["scheduled", "rescheduled"])
        ).count()

        # 📅 Fetch paginated schedules
        skip = (page - 1) * page_size
        schedules = await ScheduleDoc.find(
            ScheduleDoc.provider_id.id == prov_oid,
            ScheduleDoc.is_deleted == False,
            In(ScheduleDoc.status, ["scheduled", "rescheduled"]),
            fetch_links=True
        ).sort("appointment_datetime").skip(skip).limit(page_size).to_list()
        

        def safe_dec(val):
            try:
                return decrypt_value(ce, val).strip('"') if val else ""
            except:
                return ""

        def dec_json(val):
            try:
                if not val:
                    return None
                s = decrypt_value(ce, val)
                return json.loads(s) if isinstance(s, str) else s
            except:
                return None

        # 🏗️ Grouping by Facility (Within current page)
        facility_groups = {}

        for sch in schedules:
            fac = sch.facility_id
            patient = sch.patient_id

            # Ensure all links are fetched if fetch_links=True failed to resolve some
            if hasattr(fac, "fetch") and not hasattr(fac, "facility_name_search"):
                fac = await fac.fetch()
            if hasattr(patient, "fetch") and not hasattr(patient, "personal_information"):
                patient = await patient.fetch()

            if not fac or not patient:
                continue

            # Ensure patient's user_id link is also fetched to get name/email/phone
            pat_user = getattr(patient, "user_id", None)
            if pat_user and hasattr(pat_user, "fetch") and not hasattr(pat_user, "full_name_search"):
                pat_user = await pat_user.fetch()

            fac_id_str = str(fac.id)
            if fac_id_str not in facility_groups:
                facility_groups[fac_id_str] = {
                    "facility_id": fac_id_str,
                    "facility_name": getattr(fac, "facility_name_search", None),
                    "facility_status": getattr(fac, "status", None),
                    "appointments": []
                }

            # Decrypt patient name
            p_name = None
            if pat_user:
                p_name = getattr(pat_user, "full_name_search", None)
            
            if not p_name and patient.personal_information:
                pi = dec_json(patient.personal_information) or {}
                fn = (pi.get("first_name") or "").strip()
                ln = (pi.get("last_name") or "").strip()
                p_name = f"{fn} {ln}".strip()

            facility_groups[fac_id_str]["appointments"].append({
                "schedule_id": str(sch.id),
                "appointment_datetime": sch.appointment_datetime.isoformat() if sch.appointment_datetime else None,
                "status": sch.status,
                "notes": sch.notes,
                "patient": {
                    "id": str(patient.id),
                    "name": p_name,
                    "email": getattr(patient.user_id, "email_search", None) if patient.user_id else None,
                    "phone": getattr(patient.user_id, "phone_search", None) if patient.user_id else None,
                    "personal_information": dec_json(patient.personal_information),
                    "admission_information": dec_json(patient.admisson_information),
                    "address_information": dec_json(patient.address_information),
                    "insurance_information": dec_json(patient.insurance_information),
                    "diagnosis_information": dec_json(patient.diagnosis),
                }
            })

        provider_name = f"{safe_dec(provider.first_name)} {safe_dec(provider.last_name)}".strip()

        return {
            "success": True,
            "page": page,
            "page_size": page_size,
            "total_appointments": total_appointments,
            "total_pages": (total_appointments + page_size - 1) // page_size,
            "provider": {
                "id": str(provider.id),
                "name": provider_name,
                "status": provider.status,
            },
            "data": list(facility_groups.values())
        }

    except HTTPException:
        raise
    except Exception as e:
         print(f"❌ PROVIDER SCHEDULED PATIENTS CRASH: {e}")
         raise HTTPException(status_code=500, detail="Internal Server Error")
