from fastapi import APIRouter, Request, HTTPException, Depends, Query
from bson import ObjectId
from typing import Optional
from app.auth.deps import get_current_user_id
from app.schemas.facilityrole.facilityrole import FacilityRoleCreateSchema
from app.accounts.models.user import UserDoc
from app.facility.models.facility import Facility
from app.FacilityRole.models.user_facility_role import UserFacilityRole
from app.auth.password import hash_password
from beanie.operators import RegEx,Or,And
from datetime import datetime, timezone


from app.encryption.encryption import (
    encrypt_dict,
    init_encryption,
    ensure_data_key,
    encrypt_value_deterministic,
    encrypt_value,
    decrypt_value
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
    


    plain_password = "123456"   # 🔥 send via email in real app
    hashed_password = hash_password(plain_password)
    normalise_full_name_search = payload.name
    normalise_email_search = payload.email
    normalise_phone_search = payload.phone
    encrypted = encrypt_dict(
        ce,
        dek_id,
        {
            "name": payload.name,
            "phone": payload.phone,
            "password": hashed_password, 
            
        }
    )

    encrypted_email = encrypt_value_deterministic(
        ce, dek_id, payload.email
    )

   

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
        full_name_search =normalise_full_name_search,
        email_search = normalise_email_search,
        phone_search = normalise_phone_search
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




@router.get("/list/")
async def get_facility_user(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    try:
        # 1️⃣ User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 2️⃣ Encryption
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            
        
      

        # ----------------------------
        # 3️⃣ Query conditions (Beanie style)
        # ----------------------------
        conditions = [
            UserFacilityRole.created_by.id == user.id,
            UserFacilityRole.is_deleted == False
        ]

        if status:
            conditions.append(UserFacilityRole.status == status.lower())


        if search:
            search_value = search.lower()
            conditions.append(
                Or(
                    RegEx(UserFacilityRole.user_id.full_name_search, f"^{search_value}"),
                    RegEx(UserFacilityRole.user_id.phone_search, f"^{search_value}"),
                    RegEx(UserFacilityRole.user_id.email_search, f"^{search_value}"),
                    RegEx(UserFacilityRole.facility_id.facility_name_search, f"^{search_value}"),
                   
                )
               
            )

        

       
        
        
        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------
        user_fac_role = await (
            UserFacilityRole.find(
                *conditions,
                fetch_links=True
            )
            .sort("-created_at")
            .skip(skip)
            .limit(page_size)
            .to_list()
        )

        # ----------------------------
        # 6️⃣ Total count (IMPORTANT)
        # ----------------------------
        total = await UserFacilityRole.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------
        result = []
        for facility_role in user_fac_role:
            result.append({
                "id": str(facility_role.id),
                "full_name": decrypt_value(ce, facility_role.user_id.full_name),
                "email": decrypt_value(ce, facility_role.user_id.email),
                "phone": decrypt_value(ce, facility_role.user_id.phone),
                # "name": (
                #     facility_role.user_id.full_name
                #     if facility_role.user_id else None
                # ),
                "role": facility_role.role,
                "is_primary": facility_role.is_primary,
                "status": facility_role.status,
                "facility_id": str(facility_role.facility_id.id) if facility_role.facility_id else None,
                "facility_name": (
                    facility_role.facility_id.facility_name_search
                    if facility_role.facility_id else None
                ),

                "status": facility_role.status,
                "created_at": facility_role.created_at,
                "updated_at": facility_role.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Facility User Role",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Facility User Role fetched | "
                    f"page={page}, page_size={page_size}, "
                    f"search={search}, status={status}, "
                    f"returned={len(result)}"
                ),
            )
        except Exception:
            pass


        return {
            "success": True,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "count": len(result),
            "total": total,
            "data": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")







@router.put("/update/{user_facility_role_id}/")
async def update_facility_user(
    user_facility_role_id: str,
    payload: FacilityRoleCreateSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    # ------------------------------------
    # 1️⃣ Auth user
    # ------------------------------------
    current_user = await UserDoc.get(current_user_id)
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        user_facility_role_oid = ObjectId(user_facility_role_id)
    except InvalidId:
        raise HTTPException(
            status_code=400,
            detail="Invalid user_facility_role_id"
        )

    # ------------------------------------
    # 2️⃣ Fetch mapping
    # ------------------------------------
    user_fac_role = await UserFacilityRole.get(
        user_facility_role_oid,
        fetch_links=True
    )

    if not user_fac_role or user_fac_role.is_deleted:
        raise HTTPException(404, "Record not found")

    # ------------------------------------
    # 3️⃣ Encryption init
    # ------------------------------------
    ce = getattr(request.app, "client_encryption", None)
    if not ce:
        ce = init_encryption()
        request.app.client_encryption = ce

    dek_id = getattr(request.app, "dek_id", None)
    if not dek_id:
        dek_id = ensure_data_key()
        request.app.dek_id = dek_id

    

    target_user = user_fac_role.user_id

    # ------------------------------------
    # 4️⃣ EMAIL DUPLICATE CHECK
    # ------------------------------------
    encrypted_email = encrypt_value_deterministic(
        ce, dek_id, payload.email
    )

    existing = await UserDoc.find_one(
        UserDoc.email == encrypted_email,
        UserDoc.id != target_user.id
    )
    if existing:
        raise HTTPException(400, "Email already exists")

    # ------------------------------------
    # 5️⃣ Update USER
    # ------------------------------------
    target_user.full_name = encrypt_value(ce, dek_id, payload.name)
    target_user.full_name_search = payload.name.lower().strip()

    target_user.email = encrypted_email
    target_user.email_search = payload.email.lower().strip()

    if payload.phone:
        target_user.phone = encrypt_value(ce, dek_id, payload.phone)
        target_user.phone_search = payload.phone

    target_user.updated_at = datetime.now(timezone.utc)
    await target_user.save()

    # ------------------------------------
    # 6️⃣ Update FACILITY ROLE
    # ------------------------------------
    user_fac_role.role = payload.role
    user_fac_role.updated_at = datetime.now(timezone.utc)
    await user_fac_role.save()

    # ------------------------------------
    # 7️⃣ Audit
    # ------------------------------------
    try:
        await log_audit(
            request=request,
            user_id=str(current_user.id),
            action="Update",
            resource="Facility User",
            resource_id=str(user_fac_role.id),
            status="success",
            notes=f"Updated facility user role to {payload.role}",
        )
    except Exception:
        pass

    return {
        "success": True,
        "id": str(user_fac_role.id),
        "name": payload.name,
        "email": payload.email,
        "phone": payload.phone,
        "role": payload.role,
    }



