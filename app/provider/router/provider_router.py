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
from app.utils.s3_utils import s3_client, get_bucket_name, safe_filename, safe_folder_name, put_object
from app.facility.models.facility import Facility
from app.provider.models.practice import Practice

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
        # ------------------------------------
        # 3.a) Upload profile_pic and signature to S3
        # ------------------------------------
        s3 = s3_client()
        bucket = get_bucket_name()
        provider_folder = f"{safe_folder_name(full_name)}({str(user_doc.id)})"
        encrypted_profile_pic_key = None
        encrypted_signature_key = None

        if profile_pic is not None:
            file_bytes = await profile_pic.read()
            if file_bytes:
                key_profile = f"{provider_folder}/profile/{safe_filename(profile_pic.filename)}"
                try:
                    put_object(s3, bucket, key_profile, file_bytes, profile_pic.content_type)
                    encrypted_profile_pic_key = encrypt_value(ce, dek_id, key_profile)
                except Exception:
                    encrypted_profile_pic_key = None

        if signature is not None:
            file_bytes = await signature.read()
            if file_bytes:
                key_signature = f"{provider_folder}/signature/{safe_filename(signature.filename)}"
                try:
                    put_object(s3, bucket, key_signature, file_bytes, signature.content_type)
                    encrypted_signature_key = encrypt_value(ce, dek_id, key_signature)
                except Exception:
                    encrypted_signature_key = None

        # ------------------------------------
        # 4) Create Provider linked to user
        # ------------------------------------
        provider_doc = Provider(
            user=user_doc,
            user_id=str(user_doc.id),
            profile=encrypted_profile,
            role=encrypted_provider_role,
            profile_pic=encrypted_profile_pic_key,
            signature=encrypted_signature_key,
            created_by=current_user,
            

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


def _dec(ce, val):
    if not val:
        return None
    raw = decrypt_value(ce, val)
    return raw.decode() if isinstance(raw, (bytes, bytearray)) else raw


@router.get("/list")
async def list_providers(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    search: str = "",
    page: int = 1,
    limit: int = 10,
):
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role_val = None
    if user.role is not None:
        try:
            raw = decrypt_value(ce, user.role)
            role_val = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
        except Exception:
            role_val = None

    is_super_admin = role_val == UserRole.SUPER_ADMIN.value
    is_admin = role_val == UserRole.ADMIN.value or is_super_admin
    
    docs = (
        await Provider.find(Provider.created_by.id == user.id)
        .sort("-created_at")
        .to_list()
    )
    

    items = []
    
    q = (search or "").strip().lower()
    q_tokens = [t for t in q.split() if t]

    for p in docs:
        try:
            await p.fetch_links()
        except Exception:
            pass

        role_val_user = None
        if user.role is not None:
            try:
                raw = decrypt_value(ce, user.role)
                role_val_user = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
            except Exception:
                role_val_user = None

        is_super_admin = role_val_user == UserRole.SUPER_ADMIN.value
        is_admin = role_val_user == UserRole.ADMIN.value or is_super_admin

        u = getattr(p, "user", None)
        uid = None
        try:
            if u and getattr(u, "id", None):
                uid = str(u.id)
            else:
                refu = getattr(p.user, "ref", None) if getattr(p, "user", None) else None
                uid = str(getattr(refu, "id", None)) if refu is not None else None
        except Exception:
            uid = None
        if not uid:
            uid = getattr(p, "user_id", None)

        if not is_super_admin:
            if is_admin:
                created_by_id = None
                cb = getattr(p, "created_by", None)
                try:
                    if cb and getattr(cb, "id", None):
                        created_by_id = str(cb.id)
                    else:
                        refcb = getattr(cb, "ref", None) if cb is not None else None
                        created_by_id = str(getattr(refcb, "id", None)) if refcb is not None else None
                except Exception:
                    created_by_id = None
                if not created_by_id or created_by_id != str(user.id):
                    raise HTTPException(status_code=403, detail="Forbidden")
            else:
                if uid != str(user.id):
                    raise HTTPException(status_code=403, detail="Forbidden")

        full_name = None
        email = None
        phone = None
        if u and getattr(u, "full_name", None) is not None:
            full_name = _dec(ce, u.full_name)
            email = _dec(ce, getattr(u, "email", None))
            phone = _dec(ce, getattr(u, "phone", None))
        elif uid:
            try:
                u_doc = await UserDoc.get(uid)
                if u_doc:
                    full_name = _dec(ce, getattr(u_doc, "full_name", None))
                    email = _dec(ce, getattr(u_doc, "email", None))
                    phone = _dec(ce, getattr(u_doc, "phone", None))
            except Exception:
                pass

        profile = None
        try:
            pr_raw = decrypt_value(ce, p.profile) if p.profile else None
            if isinstance(pr_raw, (bytes, bytearray)):
                pr_raw = pr_raw.decode()
            profile = json.loads(pr_raw) if isinstance(pr_raw, str) else None
        except Exception:
            profile = None

       
        first_name = (profile or {}).get("first_name")
        middle_name = (profile or {}).get("middle_name")
        last_name = (profile or {}).get("last_name")
        degree = (profile or {}).get("degree_enum")
        speciality = (profile or {}).get("speciality")
        subspeciality = (profile or {}).get("subspeciality")
        npi_no = (profile or {}).get("npi_no")
        
        

        if q_tokens:
            blob = " ".join([
                full_name or "",
                email or "",
                phone or "",
                first_name or "",
                middle_name or "",
                last_name or "",
                degree or "",
                speciality or "",
                subspeciality or "",
                npi_no or "",
                
            ]).lower()
            ok = all(t in blob for t in q_tokens)
            if not ok:
                continue

        items.append({
            "id": str(p.id),
            "user_id": uid,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name,
            "degree": degree,
            "speciality": speciality,
            "subspeciality": subspeciality,
            "npi_no": npi_no,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        })

    total = len(items)
    if limit <= 0:
        limit = 10
    if page <= 0:
        page = 1
    start = (page - 1) * limit
    end = start + limit
    page_items = items[start:end]
    pages = (total + limit - 1) // limit

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Provider",
            resource_id="list",
            status="success",
            notes="Providers listed",
        )
    except Exception:
        pass

    return {
        "providers": page_items,
        
        "page": page,
        "limit": limit,
        "total": total,
        "pages": pages,
    }


@router.get("/get/{provider_id}/")
async def get_provider(
    provider_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        try:
            prov_oid = PydanticObjectId(provider_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid provider_id")

        p = await Provider.get(prov_oid)
        if not p:
            raise HTTPException(status_code=404, detail="Provider not found")

        try:
            await p.fetch_links()
        except Exception:
            pass

        u = getattr(p, "user", None)
        uid = None
        try:
            if u and getattr(u, "id", None):
                uid = str(u.id)
            else:
                refu = getattr(p.user, "ref", None) if getattr(p, "user", None) else None
                uid = str(getattr(refu, "id", None)) if refu is not None else None
        except Exception:
            uid = None
        if not uid:
            uid = getattr(p, "user_id", None)

        full_name = None
        email = None
        phone = None
        if u and getattr(u, "full_name", None) is not None:
            full_name = _dec(ce, u.full_name)
            email = _dec(ce, getattr(u, "email", None))
            phone = _dec(ce, getattr(u, "phone", None))
        elif uid:
            try:
                u_doc = await UserDoc.get(uid)
                if u_doc:
                    full_name = _dec(ce, getattr(u_doc, "full_name", None))
                    email = _dec(ce, getattr(u_doc, "email", None))
                    phone = _dec(ce, getattr(u_doc, "phone", None))
            except Exception:
                pass

        profile = None
        try:
            pr_raw = decrypt_value(ce, p.profile) if p.profile else None
            if isinstance(pr_raw, (bytes, bytearray)):
                pr_raw = pr_raw.decode()
            profile = json.loads(pr_raw) if isinstance(pr_raw, str) else None
        except Exception:
            profile = None

        role_val = None
        try:
            role_val = _dec(ce, getattr(p, "role", None))
        except Exception:
            role_val = None

        result = {
            "id": str(p.id),
            "user_id": uid,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "role": role_val,
            "profile": profile,
            "profile_pic": _dec(ce, getattr(p, "profile_pic", None)),
            "signature": _dec(ce, getattr(p, "signature", None)),
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Provider",
                resource_id=str(p.id),
                status="success",
                notes="Provider fetched",
            )
        except Exception:
            pass

        return result
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Read",
                resource="Provider",
                resource_id=provider_id,
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))




# ------------------------------------ facility id wise fetch providers -----------------------------------


@router.get("/list/by-facility/{facility_id}/")
async def list_providers_by_facility(
    facility_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    search: str = "",
    page: int = 1,
    limit: int = 10,
):
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    facility_obj = None
    try:
        facility_obj_id = PydanticObjectId(facility_id)
        facility_obj = await Facility.get(facility_obj_id)
    except Exception:
        facility_obj = None

    if facility_obj is None:
        try:
            facility_obj = await Facility.get(facility_id)
        except Exception:
            facility_obj = None

    if not facility_obj:
        raise HTTPException(status_code=404, detail="Facility not found")

    role_val = None
    if user.role is not None:
        try:
            r = decrypt_value(ce, user.role)
            role_val = r.decode("utf-8") if isinstance(r, (bytes, bytearray)) else r
        except Exception:
            role_val = None

    is_admin = role_val in {"admin", "super_admin"}
    if not is_admin:
        try:
            await facility_obj.fetch_link(Facility.created_by)
        except Exception:
            pass
        owner_id = getattr(getattr(facility_obj, "created_by", None), "id", None)
        if owner_id is not None and owner_id != user.id:
            raise HTTPException(status_code=403, detail="Forbidden")

    docs_link = await Practice.find({"facility_ids.$id": facility_obj.id}).to_list()
    docs_str = await Practice.find({"facility_ids": str(facility_obj.id)}).to_list()
    primary_link = await Practice.find({"primary_facility_id.$id": facility_obj.id}).to_list()
    primary_str = await Practice.find({"primary_facility_id": str(facility_obj.id)}).to_list()

    seen_practice = set()
    practices: list[Practice] = []
    for d in docs_link + docs_str + primary_link + primary_str:
        did = str(getattr(d, "id", ""))
        if not did or did in seen_practice:
            continue
        seen_practice.add(did)
        practices.append(d)

    provider_ids = []
    seen_provider = set()
    for pr in practices:
        pid = getattr(getattr(pr, "provider_id", None), "id", None)
        if pid is None:
            try:
                pid = getattr(getattr(getattr(pr, "provider_id", None), "ref", None), "id", None)
            except Exception:
                pid = None
        if pid is None:
            continue
        spid = str(pid)
        if spid in seen_provider:
            continue
        seen_provider.add(spid)
        provider_ids.append(pid)

    providers = []
    if provider_ids:
        providers = await Provider.find({"_id": {"$in": provider_ids}}).sort("-created_at").to_list()

    items = []
    q = (search or "").strip().lower()
    q_tokens = [t for t in q.split() if t]

    for p in providers:
        try:
            await p.fetch_links()
        except Exception:
            pass

        u = getattr(p, "user", None)
        uid = None
        try:
            if u and getattr(u, "id", None):
                uid = str(u.id)
            else:
                refu = getattr(p.user, "ref", None) if getattr(p, "user", None) else None
                uid = str(getattr(refu, "id", None)) if refu is not None else None
        except Exception:
            uid = None
        if not uid:
            uid = getattr(p, "user_id", None)

        full_name = None
        email = None
        phone = None
        if u and getattr(u, "full_name", None) is not None:
            full_name = _dec(ce, u.full_name)
            email = _dec(ce, getattr(u, "email", None))
            phone = _dec(ce, getattr(u, "phone", None))
        elif uid:
            try:
                u_doc = await UserDoc.get(uid)
                if u_doc:
                    full_name = _dec(ce, getattr(u_doc, "full_name", None))
                    email = _dec(ce, getattr(u_doc, "email", None))
                    phone = _dec(ce, getattr(u_doc, "phone", None))
            except Exception:
                pass

        profile = None
        try:
            pr_raw = decrypt_value(ce, p.profile) if p.profile else None
            if isinstance(pr_raw, (bytes, bytearray)):
                pr_raw = pr_raw.decode()
            profile = json.loads(pr_raw) if isinstance(pr_raw, str) else None
        except Exception:
            profile = None

        first_name = (profile or {}).get("first_name")
        middle_name = (profile or {}).get("middle_name")
        last_name = (profile or {}).get("last_name")
        degree = (profile or {}).get("degree_enum")
        speciality = (profile or {}).get("speciality")
        subspeciality = (profile or {}).get("subspeciality")

        if q_tokens:
            blob = " ".join([
                full_name or "",
                email or "",
                phone or "",
                first_name or "",
                middle_name or "",
                last_name or "",
                degree or "",
                speciality or "",
                subspeciality or "",
            ]).lower()
            ok = all(t in blob for t in q_tokens)
            if not ok:
                continue

        items.append({
            "id": str(p.id),
            "user_id": uid,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name,
            "degree": degree,
            "speciality": speciality,
            "subspeciality": subspeciality,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        })

    total = len(items)
    if limit <= 0:
        limit = 10
    if page <= 0:
        page = 1
    start = (page - 1) * limit
    end = start + limit
    page_items = items[start:end]
    pages = (total + limit - 1) // limit

    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="Provider",
            resource_id=f"facility:{str(facility_obj.id)}",
            status="success",
            notes="Providers fetched by facility",
        )
    except Exception:
        pass

    return {
        "providers": page_items,
        "page": page,
        "limit": limit,
        "total": total,
        "pages": pages,
    }


@router.put("/update/{provider_id}")
async def update_user_and_provider(
    provider_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    profile_pic: UploadFile | None = File(None),
    signature: UploadFile | None = File(None),
    full_name: str | None = Form(None),
    email: EmailStr | None = Form(None),
    phone: str | None = Form(None),
    password: str | None = Form(None),
    provider_form: dict = Depends(ProviderForm),
):
    try:
        # ------------------------------------
        # Encryption init
        # ------------------------------------
        ce = getattr(request.app, "client_encryption", None) or init_encryption()
        request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None) or ensure_data_key()
        request.app.dek_id = dek_id

        # ------------------------------------
        # Validate current user (admin)
        # ------------------------------------
        current_user = await UserDoc.get(current_user_id)
        if not current_user:
            raise HTTPException(404, "Current user not found")

        # role_raw = decrypt_value(ce, current_user.role)
        # role = role_raw.decode() if isinstance(role_raw, (bytes, bytearray)) else role_raw

        # if role not in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}:
        #     raise HTTPException(403, "Only admin can update provider users")

        # ------------------------------------
        # Fetch Provider + User
        # ------------------------------------
        provider = await Provider.get(provider_id)
        if not provider:
            raise HTTPException(404, "Provider not found")

        user = await UserDoc.get(provider.user_id)
        if not user:
            raise HTTPException(404, "Linked user not found")

        # ------------------------------------
        # Update USER fields
        # ------------------------------------
        if full_name:
            user.full_name = encrypt_value(ce, dek_id, full_name)

        if email:
            user.email = encrypt_value_deterministic(ce, dek_id, email)

        if phone:
            user.phone = encrypt_value_deterministic(ce, dek_id, phone)

        if password:
            user.password = encrypt_value(ce, dek_id, hash_password(password))

        await user.save()

        # ------------------------------------
        # Update Provider profile JSON
        # ------------------------------------
        if provider_form:
            payload = {
                k: (v.value if hasattr(v, "value") else v)
                for k, v in provider_form.items()
                if v is not None
            }
            provider.profile = encrypt_value(ce, dek_id, json.dumps(payload))

            if provider_form.get("role"):
                provider.role = encrypt_value(
                    ce, dek_id, provider_form["role"].value
                )

        # ------------------------------------
        # Upload updated files (S3)
        # ------------------------------------
        s3 = s3_client()
        bucket = get_bucket_name()

        folder_name = safe_folder_name(
            full_name or decrypt_value(ce, user.full_name)
        )
        provider_folder = f"{folder_name}({user.id})"

        if profile_pic:
            file_bytes = await profile_pic.read()
            if file_bytes:
                key = f"{provider_folder}/profile/{safe_filename(profile_pic.filename)}"
                put_object(s3, bucket, key, file_bytes, profile_pic.content_type)
                provider.profile_pic = encrypt_value(ce, dek_id, key)

        if signature:
            file_bytes = await signature.read()
            if file_bytes:
                key = f"{provider_folder}/signature/{safe_filename(signature.filename)}"
                put_object(s3, bucket, key, file_bytes, signature.content_type)
                provider.signature = encrypt_value(ce, dek_id, key)

        await provider.save()

        # ------------------------------------
        # Audit Log
        # ------------------------------------
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="UPDATE",
            resource="provider_user",
            resource_id=str(provider.id),
            status="success",
            notes="Provider + User updated",
        )

        return {
            "message": "Provider user updated successfully",
            "provider_id": str(provider.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        await log_audit(
            request=request,
            user_id=current_user_id,
            action="UPDATE",
            resource="provider_user",
            resource_id=provider_id,
            status="failed",
            notes=f"{type(e).__name__}: {e!r}",
        )
        raise HTTPException(500, str(e))
