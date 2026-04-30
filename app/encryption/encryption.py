from pymongo.encryption import ClientEncryption
from pymongo import MongoClient
from bson.binary import Binary
from bson.codec_options import CodecOptions
from app.database.config import settings
import json

KEY_VAULT_NAMESPACE = f"{settings.KEY_VAULT_DB}.{settings.KEY_VAULT_COLL}"
DEK_KEY_ALT_NAME = "healthcare_app_dek"

# Sync pymongo client for ClientEncryption
pymongo_client = MongoClient(settings.MONGO_URI)
pymongo_key_vault = pymongo_client[settings.KEY_VAULT_DB][settings.KEY_VAULT_COLL]
print("Pymongo MongoClient initialized for ClientEncryption.")


# def get_kms_providers():
#     if settings.AWS_ACCESS_KEY_ID:
#         return {
#             "aws": {
#                 "accessKeyId": settings.AWS_ACCESS_KEY_ID,
#                 "secretAccessKey": settings.AWS_SECRET_ACCESS_KEY
#             }
#         }
#     return { "aws": {"accessKeyId": None, "secretAccessKey": None} }


def get_kms_providers():
    if settings.USE_AWS_KMS:
        return {
            "aws": {
                "accessKeyId": settings.AWS_ACCESS_KEY_ID,
                "secretAccessKey": settings.AWS_SECRET_ACCESS_KEY
            }
        }
    else:
        # dummy provider (no AWS call)
        return {
            "local": {
                "key": b"0" * 96  # static local master key
            }
        }

def init_encryption():  
    kms_providers = get_kms_providers()
    return ClientEncryption(
        kms_providers,
        KEY_VAULT_NAMESPACE,
        pymongo_client,
        CodecOptions()
    )


# def ensure_data_key():
#     existing = pymongo_key_vault.find_one({"keyAltNames": DEK_KEY_ALT_NAME})
#     if existing:
#         return existing["_id"]

#     client_encryption = init_encryption()
#     master_key = {
#         "region": settings.AWS_REGION,
#         "key": settings.KMS_KEY_ARN
#     }

#     dek_id = client_encryption.create_data_key(
#         "aws",
#         master_key=master_key,
#         key_alt_names=[DEK_KEY_ALT_NAME]
#     )
#     client_encryption.close()
#     return dek_id


def ensure_data_key():
    existing = pymongo_key_vault.find_one({"keyAltNames": DEK_KEY_ALT_NAME})
    if existing:
        return existing["_id"]

    client_encryption = init_encryption()

    if settings.USE_AWS_KMS:
        master_key = {
            "region": settings.AWS_REGION,
            "key": settings.KMS_KEY_ARN
        }
        provider = "aws"
    else:
        master_key = None
        provider = "local"

    dek_id = client_encryption.create_data_key(
        provider,
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

# def decrypt_value(client_encryption, value: Binary):
    
#     return client_encryption.decrypt(value)

def encrypt_dict(client_encryption, dek_id, data: dict):
    encrypted = {}
    for key, value in data.items():
        if value is None:
            encrypted[key] = None
        else:
            encrypted[key] = encrypt_value(client_encryption, dek_id, value)
    return encrypted



def decrypt_value(client_encryption, value: Binary):
    if not value:
        return None
    raw = client_encryption.decrypt(value)
    return raw.decode() if isinstance(raw, (bytes, bytearray)) else raw



def _decrypt_json_field(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    decrypted_raw = decrypt_value(client_encryption, encrypted_val)
    if isinstance(decrypted_raw, (bytes, bytearray)):
        decrypted_raw = decrypted_raw.decode()
    return json.loads(decrypted_raw)










# def _dec_str(client_encryption, encrypted_val):
#     if not encrypted_val:
#         return None
#     raw = decrypt_value(client_encryption, encrypted_val)
#     return raw.decode() if isinstance(raw, (bytes, bytearray)) else raw





def safe_decrypt(ce, value):
    """
    Single encrypted field
    """
    if value is None:
        return None
    if isinstance(value, Binary):
        return decrypt_value(ce, value)
    return value  # already decrypted / plain


def safe_decrypt_list(ce, values):
    """
    List of encrypted fields
    """
    if not values:
        return []
    result = []
    for v in values:
        if isinstance(v, Binary):
            result.append(decrypt_value(ce, v))
        else:
            result.append(v)
    return result
