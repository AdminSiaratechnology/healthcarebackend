

from beanie import PydanticObjectId
from fastapi import APIRouter, Request, HTTPException, Depends, Form, File, UploadFile, Query
from pydantic import EmailStr
from enum import Enum
from datetime import datetime, timezone
from bson import ObjectId
import boto3
from typing import Optional
from beanie.operators import RegEx,Or,And
from app.auth.deps import get_current_user_id
from app.accounts.models.user import UserDoc, UserRole
from app.facility.models.facility import Facility
from app.provider.models.providers import Provider
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
            Provider.created_by.id == user.id,
            Provider.is_deleted == False
        ]

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
                "last_name": decrypt_value(ce, prov.last_name),
                # "phone": decrypt_value(ce, prov.user.phone),
                "degree": decrypt_value(ce, prov.degree),
                "speciality": decrypt_value(ce, prov.speciality),
                "professional_phone": decrypt_value(ce, prov.professional_phone),
                "rotation_days": rotation_days,
                "oncall_days": oncall_days,
                "profile_pic": prov.profile_pic,
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
                facility_object_ids = [
                    ObjectId(fid.strip()) for fid in facility_ids.split(",")
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
