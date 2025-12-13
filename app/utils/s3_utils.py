from fastapi import HTTPException
from app.database.config import settings
import boto3
import uuid


def get_bucket_name():
    b = settings.AWS_S3_BUCKET
    if not b:
        raise HTTPException(status_code=500, detail="AWS_S3_BUCKET env not set")
    return b


def s3_client():
    region = settings.AWS_REGION
    kwargs = {"region_name": region}
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    return boto3.client("s3", **kwargs)


def safe_filename(name: str | None) -> str:
    base = (name or "file").strip().replace(" ", "_")
    base = "".join(ch for ch in base if ch.isalnum() or ch in {"_", ".", "-"})
    uid = uuid.uuid4().hex[:8]
    if "." in base:
        root, ext = base.rsplit(".", 1)
        return f"{root}_{uid}.{ext}"
    return f"{base}_{uid}"


def safe_folder_name(name: str | None) -> str:
    base = (name or "folder").strip().lower()
    base = base.replace(" ", "_")
    base = "".join(ch for ch in base if ch.isalnum() or ch in {"_", "-"})
    return base


def put_object(s3, bucket: str, key: str, data: bytes, content_type: str | None):
    extra = {}
    kms_key = settings.KMS_KEY_ARN
    if kms_key:
        extra["ServerSideEncryption"] = "aws:kms"
        extra["SSEKMSKeyId"] = kms_key
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType=content_type or "application/octet-stream",
        **extra,
    )


def presign(s3, bucket: str, key: str, expires: int = 3600) -> str:
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )
