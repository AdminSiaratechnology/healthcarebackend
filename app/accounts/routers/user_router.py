from fastapi import APIRouter,Request,HTTPException
from app.schemas.users import Users
from app.accounts.models.user import UserDoc
from app.utils.audit import log_audit
from app.encryption.encryption import encrypt_value,decrypt_value,encrypt_value_deterministic
from app.auth.password import hash_password

# router = APIRouter()
router = APIRouter(prefix="/account", tags=["Account"])


@router.post("/users")
async def user_registrations(users: Users, request: Request):
    try:
        client_encryption = request.app.client_encryption
        dek_id = request.app.dek_id
        if users.email:
            encrypted_email = encrypt_value_deterministic(client_encryption, dek_id, users.email)
            existing_email_user = await UserDoc.find_one({"email": encrypted_email})
            if existing_email_user:
                raise HTTPException(status_code=400, detail="Email already exists")

        encrypted_doc = {
            'full_name': encrypt_value(client_encryption, dek_id, users.full_name),

            'email': encrypt_value_deterministic(client_encryption, dek_id, users.email)
                      if users.email else None,

            'phone': encrypt_value_deterministic(client_encryption, dek_id, users.phone)
                     if users.phone else None,

            'role': encrypt_value(client_encryption, dek_id, users.role.value),

            'password': encrypt_value(client_encryption, dek_id, hash_password(users.password))
                                if hash_password(users.password) else None
        }

        user = UserDoc(**encrypted_doc)
        await user.insert()
        # raw = decrypt_value(client_encryption, user.role)
        # role = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        # print("rolessssssss",role)
        

        await log_audit(
            request=request,
            action="CREATE",
            resource="patient",
            resource_id=str(user.id),
            status="success",
            notes="Patient encrypted data inserted"
        )

        return {
            "inserted_id": str(user.id),
            "user": "User saved successfully!"
        }

    except Exception as e:
        await log_audit(
            request=request,
            action="CREATE",
            resource="patient",
            resource_id="N/A",
            status="failed",
            notes=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users")
async def get_users(request: Request):
    client_encryption = request.app.client_encryption

    users = await UserDoc.find().to_list()

    decrypted_users = [u.decrypt_fields(client_encryption) for u in users]

    return {"data": decrypted_users}
