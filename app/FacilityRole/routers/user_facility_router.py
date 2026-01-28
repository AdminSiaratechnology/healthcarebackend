from fastapi import APIRouter, Request, HTTPException, Depends
from bson import ObjectId

from app.auth.deps import get_current_user_id
from app.schemas.facilityrole.facilityrole import FacilityRoleCreateSchema
from app.accounts.models.user import UserDoc
from app.facility.models.facility import Facility
from app.FacilityRole.models.user_facility_role import UserFacilityRole
from app.auth.password import hash_password
from app.encryption.encryption import (
    encrypt_dict,
    init_encryption,
    ensure_data_key,
    encrypt_value_deterministic,
    encrypt_value
)
from app.utils.audit import log_audit

router = APIRouter(prefix="/facility-roles", tags=["Facility-Roles"])


# @router.post("/create/{facility_id}/")
# async def create_user_facility_role(
#     facility_id: str,
#     payload: FacilityRoleCreateSchema,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     # 1️⃣ Logged-in user
#     current_user = await UserDoc.get(current_user_id)
#     if not current_user:
#         raise HTTPException(401, "Invalid user")

#     try:
#         facility_obj_id = ObjectId(facility_id)
#     except Exception:
#         raise HTTPException(status_code=400, detail="Invalid Facility ID format")

#     # 2️⃣ Facility
#     facility = await Facility.get(facility_obj_id)
#     if not facility:
#         raise HTTPException(404, "Facility not found")

#     # 3️⃣ Encryption init (PII only)
#     ce = getattr(request.app, "client_encryption", None)
#     if ce is None:
#         ce = init_encryption()
#         request.app.client_encryption = ce

#     dek_id = getattr(request.app, "dek_id", None)
#     if dek_id is None:
#         dek_id = ensure_data_key()
#         request.app.dek_id = dek_id

#     plain_password = "123456"   
#     hashed_password = hash_password(plain_password)

#     encrypted = encrypt_dict(
#         ce,
#         dek_id,
#         {
#             "name": payload.name,
#             "email": payload.email,
#             "phone": payload.phone,
#             "password": hashed_password, 
            
#         }
#     )

#     # 4️⃣ Duplicate user check (email)
    
#     existing_user = await UserDoc.find_one(
#         UserDoc.email == encrypted["email"]
#     )
#     if existing_user:
#         raise HTTPException(400, "User with this email already exists")

#     # 5️⃣ Create LOGIN USER
    
   
    
#     new_user = UserDoc(
#         full_name=encrypted["name"],
#         email=encrypted["email"],
#         phone=encrypted["phone"],
#         password=encrypted["password"],   # ✅ already string
        
#     )
#     await new_user.insert()

#     # 6️⃣ Assign FACILITY ROLE
#     existing_mapping = await UserFacilityRole.find_one(
#         UserFacilityRole.user_id.id == new_user.id,
#         UserFacilityRole.facility_id.id == facility.id,
#         UserFacilityRole.is_deleted == False,
#     )
#     if existing_mapping:
#         raise HTTPException(400, "Role already assigned")

#     facility_role = UserFacilityRole(
#         user_id=new_user,
#         facility_id=facility,
#         role=payload.role,
#         is_primary=True,
#         created_by=current_user,
#     )
#     await facility_role.insert()

#     # 7️⃣ Audit
#     try:
#         await log_audit(
#             request=request,
#             user_id=str(current_user.id),
#             action="Create",
#             resource="FacilityRole",
#             resource_id=str(facility_role.id),
#             status="success",
#             notes="Facility role created",
#         )
#     except Exception:
#         pass

#     return {
#         "success": True,
#         "facility_id": str(facility.id),
#         "user_id": str(new_user.id),
#         "role": payload.role,
#           # 🔥 send via email in real app
#     }




@router.post("/create/{facility_id}/")
async def create_user_facility_role(
    facility_id: str,
    payload: FacilityRoleCreateSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    # --------------------------------------------------
    # 1️⃣ Logged-in user
    # --------------------------------------------------
    current_user = await UserDoc.get(current_user_id)
    if not current_user:
        raise HTTPException(status_code=401, detail="Invalid user")

    # --------------------------------------------------
    # 2️⃣ Facility ID validation
    # --------------------------------------------------
    try:
        facility_obj_id = ObjectId(facility_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Facility ID format")

    facility = await Facility.get(facility_obj_id)
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")

    # --------------------------------------------------
    # 3️⃣ Encryption init
    # --------------------------------------------------
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    dek_id = getattr(request.app, "dek_id", None)
    if dek_id is None:
        dek_id = ensure_data_key()
        request.app.dek_id = dek_id

    # --------------------------------------------------
    # 4️⃣ Prepare encrypted fields
    # --------------------------------------------------
    encrypted_email = encrypt_value_deterministic(
        ce, dek_id, payload.email
    )


    plain_password = "123456"   # 🔥 send via email in real app
    hashed_password = hash_password(plain_password)
    encrypted = encrypt_dict(
        ce,
        dek_id,
        {
            "name": payload.name,
            "phone": payload.phone,
            "password": hashed_password, 
            
        }
    )

    # encrypted_phone = (
    #     encrypt_value_deterministic(ce, dek_id, payload.phone)
    #     if payload.phone else None
    # )

    # encrypted_name = encrypt_value(
    #     ce, dek_id, payload.name
    # )

   

    # --------------------------------------------------
    # 5️⃣ Duplicate EMAIL check ✅ FIXED
    # --------------------------------------------------
    existing_user = await UserDoc.find_one(
        UserDoc.email == encrypted_email
    )
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="User with this email already exists"
        )

    # --------------------------------------------------
    # 6️⃣ Create LOGIN USER
    # --------------------------------------------------
    new_user = UserDoc(
        full_name=encrypted["name"],
        email=encrypted_email,
        phone=encrypted["phone"],
        password=encrypted["password"],
    )
    await new_user.insert()

    # --------------------------------------------------
    # 7️⃣ Assign FACILITY ROLE
    # --------------------------------------------------
    existing_mapping = await UserFacilityRole.find_one(
        UserFacilityRole.user_id.id == new_user.id,
        UserFacilityRole.facility_id.id == facility.id,
        UserFacilityRole.is_deleted == False,
    )
    if existing_mapping:
        raise HTTPException(
            status_code=400,
            detail="Role already assigned"
        )

    facility_role = UserFacilityRole(
        user_id=new_user,
        facility_id=facility,
        role=payload.role,
        is_primary=True,
        created_by=current_user,
    )
    await facility_role.insert()

    # --------------------------------------------------
    # 8️⃣ Audit log
    # --------------------------------------------------
    try:
        await log_audit(
            request=request,
            user_id=str(current_user.id),
            action="Create",
            resource="FacilityRole",
            resource_id=str(facility_role.id),
            status="success",
            notes="Facility role created",
        )
    except Exception:
        pass

    # --------------------------------------------------
    # 9️⃣ Response
    # --------------------------------------------------
    return {
        "success": True,
        "facility_id": str(facility.id),
        "user_id": str(new_user.id),
        "role": payload.role,
        "temp_password": plain_password,  # 🔥 email karo real app me
    }