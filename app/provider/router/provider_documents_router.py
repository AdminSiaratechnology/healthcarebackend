from fastapi import APIRouter, Request, HTTPException, Depends
from app.auth.deps import get_current_user_id
from app.accounts.models.user import UserDoc
from beanie import PydanticObjectId
from app.encryption.encryption import decrypt_value, init_encryption
from app.provider.models.providers import Provider
from app.utils.audit import log_audit
from app.database.config import settings
from fastapi import Form, UploadFile, File
import os
import boto3
import uuid

router = APIRouter(prefix="/provider", tags=["Providers"])


def _get_bucket_name():
    b = settings.AWS_S3_BUCKET
    if not b:
        raise HTTPException(status_code=500, detail="AWS_S3_BUCKET env not set")
    return b


# def _s3_client():
#     region = settings.AWS_REGION
#     kwargs = {"region_name": region}
#     if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
#         kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
#         kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
#     return boto3.client("s3", **kwargs)
from botocore.config import Config

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



def _safe_filename(name: str | None) -> str:
    base = (name or "file").strip().replace(" ", "_")
    base = "".join(ch for ch in base if ch.isalnum() or ch in {"_", ".", "-"})
    uid = uuid.uuid4().hex[:8]
    if "." in base:
        root, ext = base.rsplit(".", 1)
        return f"{root}_{uid}.{ext}"
    return f"{base}_{uid}"


# def _put_object(s3, bucket: str, key: str, data: bytes, content_type: str | None):
#     extra = {}
#     kms_key = settings.KMS_KEY_ARN
#     if kms_key:
#         extra["ServerSideEncryption"] = "aws:kms"
#         extra["SSEKMSKeyId"] = kms_key
#     s3.put_object(
#         Bucket=bucket,
#         Key=key,
#         Body=data,
#         ContentType=content_type or "application/octet-stream",
#         **extra,
#     )

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



def _presign(s3, bucket: str, key: str, expires: int = 3600) -> str:
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )


def _user_role_val(ce, user: UserDoc) -> str | None:
    if user.role is None:
        return None
    try:
        raw = decrypt_value(ce, user.role)
        return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
    except Exception:
        return None


@router.post("/Upload/Documents")
async def upload_provider_documents(
    request: Request,
    provider_id: str = Form(...),
    current_user_id: str = Depends(get_current_user_id),
    medical_license: UploadFile | None = File(None),
    dea_certificate: UploadFile | None = File(None),
    board_certificate: UploadFile | None = File(None),
    malpractice_proof: UploadFile | None = File(None),
    w9form: UploadFile | None = File(None),
    cv: UploadFile | None = File(None),
    cme_certificates: UploadFile | None = File(None),
    employment_agreement: UploadFile | None = File(None),
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
        provider = await Provider.get(prov_oid)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        role_val = _user_role_val(ce, user)
        is_admin = role_val in {"admin", "super_admin"}
        if not is_admin and provider.user_id != str(user.id):
            raise HTTPException(status_code=403, detail="Forbidden")

        bucket = _get_bucket_name()
        s3 = _s3_client()

        base_prefix = f"provider documents/{str(provider.id)}"
        files_map = {
            "medical_license": medical_license,
            "dea_certificate": dea_certificate,
            "board_certificate": board_certificate,
            "malpractice_proof": malpractice_proof,
            "w9form": w9form,
            "cv": cv,
            "cme_certificates": cme_certificates,
            "employment_agreement": employment_agreement,
        }

        uploaded = {}
        for folder, up in files_map.items():
            if up is None:
                continue
            data = await up.read()
            if not data:
                continue
            fname = _safe_filename(up.filename)
            key = f"{base_prefix}/{folder}/{fname}"
            _put_object(s3, bucket, key, data, up.content_type)
            url = _presign(s3, bucket, key)
            uploaded[folder] = {
                "key": key,
                "url": url,
                "filename": up.filename,
                "content_type": up.content_type,
            }

        await log_audit(
            request=request,
            user_id=current_user_id,
            action="CREATE",
            resource="provider_documents",
            resource_id=str(provider.id),
            status="success",
            notes=f"Uploaded {len(uploaded)} documents to S3",
        )

        return {"provider_id": str(provider.id), "uploaded": uploaded}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="CREATE",
                resource="provider_documents",
                resource_id=provider_id,
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{provider_id}")
async def list_provider_documents(
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
        provider = await Provider.get(prov_oid)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        role_val = _user_role_val(ce, user)
        is_admin = role_val in {"admin", "super_admin"}
        if not is_admin and provider.user_id != str(user.id):
            raise HTTPException(status_code=403, detail="Forbidden")

        bucket = _get_bucket_name()
        s3 = _s3_client()

        base_prefix = f"provider documents/{str(provider.id)}/"
        resp = s3.list_objects_v2(Bucket=bucket, Prefix=base_prefix)
        contents = resp.get("Contents", []) or []

        items = []
        for obj in contents:
            key = obj.get("Key")
            if not key:
                continue
            parts = key[len(base_prefix):].split("/")
            if len(parts) < 2:
                continue
            folder = parts[0]
            url = _presign(s3, bucket, key)
            items.append({
                "key": key,
                "folder": folder,
                "url": url,
                "size": obj.get("Size"),
                "last_modified": obj.get("LastModified"),
            })

        await log_audit(
            request=request,
            user_id=current_user_id,
            action="READ",
            resource="provider_documents",
            resource_id=str(provider.id),
            status="success",
            notes=f"Listed {len(items)} documents from S3",
        )

        return {"provider_id": str(provider.id), "documents": items}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="READ",
                resource="provider_documents",
                resource_id=provider_id,
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))



@router.put("/documents/{provider_id}")
async def update_provider_document(
    provider_id: str,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    medical_license: UploadFile | None = File(None),
    dea_certificate: UploadFile | None = File(None),
    board_certificate: UploadFile | None = File(None),
    malpractice_proof: UploadFile | None = File(None),
    w9form: UploadFile | None = File(None),
    cv: UploadFile | None = File(None),
    cme_certificates: UploadFile | None = File(None),
    employment_agreement: UploadFile | None = File(None),
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
        provider = await Provider.get(prov_oid)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        role_val = _user_role_val(ce, user)
        is_admin = role_val in {"admin", "super_admin"}
        if not is_admin and provider.user_id != str(user.id):
            raise HTTPException(status_code=403, detail="Forbidden")

        bucket = _get_bucket_name()
        s3 = _s3_client()

        base_prefix = f"provider documents/{str(provider.id)}"
        files_map = {
            "medical_license": medical_license,
            "dea_certificate": dea_certificate,
            "board_certificate": board_certificate,
            "malpractice_proof": malpractice_proof,
            "w9form": w9form,
            "cv": cv,
            "cme_certificates": cme_certificates,
            "employment_agreement": employment_agreement,
        }

        uploaded = {}
        for folder, up in files_map.items():
            if up is None:
                continue
            data = await up.read()
            if not data:
                continue
            fname = _safe_filename(up.filename)
            key = f"{base_prefix}/{folder}/{fname}"
            _put_object(s3, bucket, key, data, up.content_type)
            url = _presign(s3, bucket, key)
            uploaded[folder] = {
                "key": key,
                "url": url,
                "filename": up.filename,
                "content_type": up.content_type,
            }

        await log_audit(
            request=request,
            user_id=current_user_id,
            action="UPDATE",
            resource="provider_documents",
            resource_id=str(provider.id),
            status="success",
            notes=f"Updated {len(uploaded)} documents",
        )

        return {"provider_id": str(provider.id), "uploaded": uploaded}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=current_user_id,
                action="UPDATE",
                resource="provider_documents",
                resource_id=provider_id,
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))





