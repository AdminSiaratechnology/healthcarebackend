from pymongo.encryption import ClientEncryption
from pymongo import MongoClient
from bson.binary import Binary
from bson.codec_options import CodecOptions
from app.database.config import settings


KEY_VAULT_NAMESPACE = f"{settings.KEY_VAULT_DB}.{settings.KEY_VAULT_COLL}"
DEK_KEY_ALT_NAME = "healthcare_app_dek"

# Sync pymongo client for ClientEncryption
pymongo_client = MongoClient(settings.MONGO_URI)
pymongo_key_vault = pymongo_client[settings.KEY_VAULT_DB][settings.KEY_VAULT_COLL]


def get_kms_providers():
    if settings.AWS_ACCESS_KEY_ID:
        return {
            "aws": {
                "accessKeyId": settings.AWS_ACCESS_KEY_ID,
                "secretAccessKey": settings.AWS_SECRET_ACCESS_KEY
            }
        }
    return { "aws": {"accessKeyId": None, "secretAccessKey": None} }




def init_encryption():
    kms_providers = get_kms_providers()
    return ClientEncryption(
        kms_providers,
        KEY_VAULT_NAMESPACE,
        pymongo_client,
        CodecOptions()
    )


def ensure_data_key():
    existing = pymongo_key_vault.find_one({"keyAltNames": DEK_KEY_ALT_NAME})
    if existing:
        return existing["_id"]

    client_encryption = init_encryption()
    master_key = {
        "region": settings.AWS_REGION,
        "key": settings.KMS_KEY_ARN
    }

    dek_id = client_encryption.create_data_key(
        "aws",
        master_key=master_key,
        key_alt_names=[DEK_KEY_ALT_NAME]
    )
    client_encryption.close()
    return dek_id


def encrypt_value(client_encryption, key_id, value):
    return client_encryption.encrypt(
        value,
        "AEAD_AES_256_CBC_HMAC_SHA_512-Random",
        key_id=key_id
    )

def encrypt_value_deterministic(client_encryption, key_id, value):
    return client_encryption.encrypt(
        value,
        "AEAD_AES_256_CBC_HMAC_SHA_512-Deterministic",
        key_id=key_id
    )

def decrypt_value(client_encryption, value: Binary):
    
    return client_encryption.decrypt(value)


