from typing import ClassVar, Set
from app.encryption.encryption import encrypt_value

class AutoEncryptMixin:
    """
    Mixin to automatically encrypt fields marked as `encrypted_fields`
    """
    encrypted_fields: ClassVar[Set[str]] = set()

    def encrypt_fields(self, client_encryption, key_id):
        """
        Encrypt all fields in `encrypted_fields` using ClientEncryption
        """
        encrypted_data = {}
        for field in self.encrypted_fields:
            val = getattr(self, field, None)
            if val is not None:
                # If field is an Enum, use its value
                if hasattr(val, "value"):
                    val = val.value
                encrypted_data[field] = encrypt_value(client_encryption, key_id, val)
            else:
                encrypted_data[field] = None
        return encrypted_data
