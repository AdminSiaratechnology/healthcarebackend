from typing import ClassVar, Set
from bson.binary import Binary
from app.encryption.encryption import decrypt_value

class AutoDecryptMixin:
    """
    Mixin to automatically decrypt fields marked as `encrypted_fields`
    """
    encrypted_fields: ClassVar[Set[str]] = set()

    def decrypt_fields(self, client_encryption):
        decrypted = {}
        for field in self.encrypted_fields:
            val = getattr(self, field, None)
            if isinstance(val, Binary):
                decrypted[field] = decrypt_value(client_encryption, val)
            else:
                decrypted[field] = val
        return decrypted
