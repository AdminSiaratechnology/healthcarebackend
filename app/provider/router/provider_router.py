from fastapi import APIRouter,Request,HTTPException, Depends
from app.schemas.provider.basic import BasicInfo
from pydantic import EmailStr
import json
from app.auth.deps import get_current_user_id
from app.accounts.models.user import UserDoc, UserRole
from beanie import PydanticObjectId
from app.encryption.encryption import encrypt_value,decrypt_value,encrypt_value_deterministic, init_encryption, ensure_data_key
from app.provider.models.providers import Provider
from app.utils.audit import log_audit
from fastapi import Form, UploadFile, File
from app.auth.password import hash_password
from enum import Enum

router = APIRouter(prefix="/provider", tags=["Providers"])


class Role(str,Enum):
    Physician = "Physician (MD/DO)"
    Nurse_practitioner = "(NP)"
    physician_assistant = "Physician Assistant (PA)"
    Psychiatrist = "Psychiatrist"
    wound_care_specialist = "Wound Care Specialist"
    podiatrist = "Podiatrist"

class DegreeEnum(str, Enum):
    MD = "MD- Doctor of Medicine"
    DO = "DO-Doctor of Osteopathic Medicine"
    NP = "Nurse Practitioner"
    PA = "Physicain Assistant"

class Speciality(str, Enum):
    
    InternalMedicine = "Internal Medicine"
    family_medicine = "Family Medicine"
    cardiology = "Cardiology"
    geriatric_medicine = "Geriatric Medicine"
    emergency_medicine = "Emergency Medicine"
    

def ProviderForm(
    first_name: str = Form(None),
    middle_name: str = Form(None),
    last_name: str = Form(None),
    degree_enum: DegreeEnum | None = Form(None),
    speciality: Speciality | None = Form(None),
    subspeciality: str = Form(None),
    npi_no: str = Form(None),
    taxonomy_code: str = Form(None),
    license_no : str = Form(None),
    license_state : str = Form(None),
    dea_no : str = Form(None),
    dea_expiration_date : str = Form(None),
    professional_email: str = Form(None),
    professional_phone: str = Form(None),
    role: Role = Form(...),
):
    return {
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "degree_enum": degree_enum,
        "speciality": speciality,
        "subspeciality": subspeciality,
        "npi_no": npi_no, 
        "taxonomy_code": taxonomy_code, 
        "license_no": license_no, 
        "license_state": license_state, 
        "dea_no": dea_no, 
        "dea_expiration_date": dea_expiration_date, 
        
        "professional_email": professional_email,
        "professional_phone": professional_phone,
        "role" : role
    }



@router.post("/create")
async def create_user_and_provider(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    profile_pic: UploadFile | None = File(None),
    signature :  UploadFile | None = File(None),
    full_name: str = Form(...),
    email: EmailStr | None = Form(None),
    phone: str | None = Form(None),
    password: str | None = Form(None),
    provider_form: dict = Depends(ProviderForm),
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce
        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        # -------------------------------
        # 1) Validate current user (admin or super admin)
        # -------------------------------
        current_user = await UserDoc.get(current_user_id)
        if not current_user:
            raise HTTPException(404, "Current user not found")

        cur_role = None
        if current_user.role is not None:
            try:
                cur_role_raw = decrypt_value(ce, current_user.role)
                cur_role = cur_role_raw.decode() if isinstance(cur_role_raw, (bytes, bytearray)) else cur_role_raw
            except Exception:
                cur_role = None

        is_admin = cur_role in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}
        if not is_admin:
            raise HTTPException(403, "Only admin can create provider users")

        # ------------------------------------
        # 2) Create USER (role = provider)
        # ------------------------------------
        encrypted_full_name = encrypt_value(ce, dek_id, full_name)
        encrypted_email = encrypt_value_deterministic(ce, dek_id, email) if email is not None else None
        encrypted_phone = encrypt_value_deterministic(ce, dek_id, phone) if phone is not None else None
        encrypted_role = encrypt_value(ce, dek_id, UserRole.PROVIDER.value)
        # encrypted_password = encrypt_value(ce, dek_id, password) if password is not None else None
        encrypted_password = (
            encrypt_value(ce, dek_id, hash_password(password))
            if password
            else None
        )


        user_doc = UserDoc(
            full_name=encrypted_full_name,
            email=encrypted_email,
            phone=encrypted_phone,
            password=encrypted_password,
            role=encrypted_role,
            is_active=True,
        )
        await user_doc.insert()

        # ------------------------------------
        # 3) Encrypt provider profile
        # ------------------------------------
        # Normalize enum values for JSON serialization
        profile_payload = {k: (v.value if hasattr(v, "value") else v) for k, v in provider_form.items()}
        profile_json = json.dumps(profile_payload)
        encrypted_profile = encrypt_value(ce, dek_id, profile_json)
        encrypted_provider_role = encrypt_value(ce, dek_id, (provider_form.get("role").value if provider_form.get("role") else None))
        encrypted_profile_pic = None
        if profile_pic is not None:
            file_bytes = await profile_pic.read()
            if file_bytes:
                encrypted_profile_pic = encrypt_value(ce, dek_id, file_bytes)
        if signature is not None:
            file_bytes = await signature.read()
            if file_bytes:
                encrypted_profile_pic = encrypt_value(ce, dek_id, file_bytes)

        # ------------------------------------
        # 4) Create Provider linked to user
        # ------------------------------------
        provider_doc = Provider(
            user=user_doc,
            user_id=str(user_doc.id),
            profile=encrypted_profile,
            role=encrypted_provider_role,
            profile_pic=encrypted_profile_pic,
            signature=encrypted_profile_pic,

        )
        await provider_doc.insert()

        # ------------------------------------
        # 5) Audit Log
        # ------------------------------------
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="CREATE",
            resource="provider_user",
            resource_id=str(provider_doc.id),
            status="success",
            notes="Provider + User created",
        )

        return {
            "message": "Provider user created successfully",
            "user_id": str(user_doc.id),
            "provider_id": str(provider_doc.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="CREATE",
                resource="provider_user",
                resource_id="N/A",
                status="failed",
                notes=f"{type(e).__name__}: {e!r}",
            )
        except Exception:
            pass
        detail = str(e) if str(e) else f"{type(e).__name__}"
        raise HTTPException(500, detail)
    





# ------------------------------------------------------------ Credentials ----------------------------------------


