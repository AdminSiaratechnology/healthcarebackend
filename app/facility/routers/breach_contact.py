from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility
from app.facility.models.facility_rooms import FacilityRooms
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key,encrypt_dict
from app.utils.audit import log_audit
from app.schemas.facilities.breach_contact import BreachContactsSchema
from bson import ObjectId
from app.facility.models.facility_breach_contact import BrachResponseContactDocs
from beanie.operators import RegEx,Or,And
from typing import Annotated, Optional


router = APIRouter(prefix="/breach-contact", tags=["Facility-Breach-Contact"]) 

# @router.post("/breach-contact/create/{facility_id}/")
# async def create_breach_contact(
#     facility_id: str,
#     payload: BreachContactsSchema,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce
#         dek_id = getattr(request.app, "dek_id", None)
#         if dek_id is None:
#             dek_id = ensure_data_key()
#             request.app.dek_id = dek_id

#         try:
#             facility_obj_id = PydanticObjectId(facility_id)
#         except Exception:
#             raise HTTPException(status_code=400, detail="Invalid Facility ID format")

#         facility = await Facility.get(facility_obj_id)
#         if not facility:
#             raise HTTPException(status_code=404, detail="Facility not found")

#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         enc_name = encrypt_value(ce, dek_id, payload.name) if payload.name is not None else None
#         enc_role = encrypt_value(ce, dek_id, payload.Role) if payload.Role is not None else None
#         enc_phone = encrypt_value(ce, dek_id, payload.phone) if payload.phone is not None else None
#         enc_email = encrypt_value(ce, dek_id, payload.email) if payload.email is not None else None

#         doc = BrachResponseContactDocs(
#             facility_id=facility,
#             name=enc_name,
#             Role=enc_role,
#             phone=enc_phone,
#             email=enc_email,
#             created_by=user,
#             created_at=datetime.now(timezone.utc),
#             updated_at=datetime.now(timezone.utc),
#         )
#         await doc.insert()

#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Create",
#             resource="Breach Contact",
#             resource_id=str(doc.id),
#             status="success",
#             notes="Breach contact created",
#         )

#         return {"status":"success","id": str(doc.id)}
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=current_user_id,
#                 action="Create",
#                 resource="Breach Contact",
#                 resource_id="N/A",
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail=str(e))




@router.post("/create/{facility_id}/")
async def create_breach_contact(
    facility_id: str,
    payload: BreachContactsSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # 1️⃣ User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 2️⃣ Encryption init
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        # 3️⃣ Facility ownership check
        facility = await Facility.find_one({
            "_id": ObjectId(facility_id),
            "created_by.$id": ObjectId(user.id),
            # "is_deleted": False
        })
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        # 4️⃣ Normalize name (VERY IMPORTANT)
        normalized_name = payload.name.strip().lower()
        normalized_phone = payload.phone.strip().lower()
        normalized_email = payload.email.strip().lower()

        # 5️⃣ Deterministic encryption (duplicate check)
       
        # 6️⃣ Duplicate validation (ACTIVE RECORDS ONLY)
        existing = await BrachResponseContactDocs.find_one({
            "facility_id.$id": facility.id,
            "name_search": normalized_name,
            # "is_deleted": False
        })

        

        if existing:
            raise HTTPException(
                status_code=400,
                detail="name already exists in this facility"
            )

        # 7️⃣ Random encryption (actual storage)
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "name": payload.name,
                "Role": payload.Role,
                "phone": payload.phone,
                "email": payload.email,
            }
        )

        # 8️⃣ Save
        breach_cont = BrachResponseContactDocs(
            name_search=normalized_name,        # 🔎 search
            phone_search=normalized_phone,        # 🔎 search
            email_search=normalized_email,        # 🔎 search
            name=encrypted["name"],
            Role=encrypted["Role"],
            phone=encrypted["phone"],
            email=encrypted["email"],
            facility_id=facility,
            created_by=user,
            status="active",
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await breach_cont.insert()

        # 9️⃣ Audit
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="CREATE",
                resource="brach_contact",
                resource_id=str(breach_cont.id),
                status="success",
            )
        except Exception:
            pass

        return {
            "success": True,
            "breach_contact_id": str(breach_cont.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")


# @router.get("/breach-contact/get/{facility_id}/")
# async def get_breach_contacts(
#     facility_id: str,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
        

#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         facility_obj = None
#         try:
#             facility_obj_id = PydanticObjectId(facility_id)
#             facility_obj = await Facility.get(facility_obj_id)
#         except Exception:
#             pass
#         if facility_obj is None:
#             facility_obj = await Facility.get(facility_id)
#         if not facility_obj:
#             raise HTTPException(status_code=404, detail="Facility not found")

#         # ---------------- ENCRYPTION ----------------
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce

#         # ---------------- Breach Contact  ----------------
#         breach_con = await BrachResponseContactDocs.find(
#             BrachResponseContactDocs.facility_id.id == facility_obj.id,
#             BrachResponseContactDocs.created_by.id == user.id
#         ).sort("-created_at").to_list()


#         # ---------------- RESPONSE ----------------
        

#         result = [
#             {
#                 "id": str(bc.id),
#                 "name": _decrypt_value(ce, bc.name),
#                 "Role": _decrypt_value(ce, bc.Role),
#                 "phone": _decrypt_value(ce, bc.phone),
#                 "email": _decrypt_value(ce, bc.email),
#                 "created_at": bc.created_at,
#                 "updated_at": bc.updated_at,
#             } for bc in breach_con
#         ]

#         try:
#             await log_audit(
#                 request=request,
#                 user_id=str(user.id),
#                 action="Read",
#                 resource="Breach Contact",
#                 resource_id=str(facility_obj.id),
#                 status="success",
#                 notes="Breach contacts fetched",
#             )
#         except Exception:
#             pass

#         return result
#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=current_user_id,
#                 action="Read",
#                 resource="Breach Contact",
#                 resource_id=facility_id,
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail=str(e))




@router.get("/list/")
async def get_breach_contacts(
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
            request.app.client_encryption = ce

        # ----------------------------
        # 3️⃣ Query conditions (Beanie style)
        # ----------------------------
        conditions = [
            BrachResponseContactDocs.created_by.id == user.id,
            BrachResponseContactDocs.is_deleted == False
        ]

        if status:
            conditions.append(BrachResponseContactDocs.status == status.lower())

        if search:
            search_value = search.lower()
            conditions.append(
                Or(
                    RegEx(BrachResponseContactDocs.name_search, f"^{search_value}"),
                    RegEx(BrachResponseContactDocs.phone_search, f"^{search_value}"),
                    RegEx(BrachResponseContactDocs.email_search, f"^{search_value}"),
                    RegEx(BrachResponseContactDocs.facility_id.facility_name_search, f"^{search_value}"),
                   
                )
               
            )
        
        
        # ----------------------------
        # 4️⃣ Pagination
        # ----------------------------
        skip = (page - 1) * page_size

        # ----------------------------
        # 5️⃣ Fetch data
        # ----------------------------
        breach_contact = await (
            BrachResponseContactDocs.find(
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
        total = await BrachResponseContactDocs.find(*conditions).count()

        # ----------------------------
        # 7️⃣ Response
        # ----------------------------
        result = []
        for breach in breach_contact:
            result.append({
                "id": str(breach.id),
                "breach_name": decrypt_value(ce, breach.name),
                "Role": decrypt_value(ce, breach.Role),
                "phone": decrypt_value(ce, breach.phone),
                "email": decrypt_value(ce, breach.email),
                "facility_id": str(breach.facility_id.id) if breach.facility_id else None,
                "facility_name": (
                    breach.facility_id.facility_name_search
                    if breach.facility_id else None
                ),
                "status": breach.status,
                "created_at": breach.created_at,
                "updated_at": breach.updated_at,
            })

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="Facility Breach Contact",
                resource_id="LIST",
                status="success",
                notes=(
                    f"Breach Contact fetched | "
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




# @router.put("/breach-contact/update/{contact_id}/")
# async def update_breach_contact(
#     contact_id: str,
#     payload: BreachContactsSchema,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         ce = getattr(request.app, "client_encryption", None)
#         if ce is None:
#             ce = init_encryption()
#             request.app.client_encryption = ce
#         dek_id = getattr(request.app, "dek_id", None)
#         if dek_id is None:
#             dek_id = ensure_data_key()
#             request.app.dek_id = dek_id

#         contact_obj = await BrachResponseContactDocs.get(contact_id)
#         if not contact_obj:
#             raise HTTPException(status_code=404, detail="Breach Contact not found")

#         if payload.name is not None:
#             contact_obj.name = encrypt_value(ce, dek_id, payload.name)
#         if payload.Role is not None:
#             contact_obj.Role = encrypt_value(ce, dek_id, payload.Role)
#         if payload.phone is not None:
#             contact_obj.phone = encrypt_value(ce, dek_id, payload.phone)
#         if payload.email is not None:
#             contact_obj.email = encrypt_value(ce, dek_id, payload.email)

#         contact_obj.updated_at = datetime.now(timezone.utc)

#         await contact_obj.save()

#         await log_audit(
#             request=request,
#             user_id=current_user_id,
#             action="Update",
#             resource="Breach Contact",
#             resource_id=str(contact_obj.id),
#             status="success",
#             notes="Breach contact updated",
#         )

#         return {"status":"success","id": str(contact_obj.id)}
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         try:
#             await log_audit(
#                 request=request,
#                 user_id=current_user_id,
#                 action="Update",
#                 resource="Breach Contact",
#                 resource_id=contact_id,
#                 status="failed",
#                 notes=str(e),
#             )
#         except Exception:
#             pass
#         raise HTTPException(status_code=500, detail=str(e)) 







@router.put("/update/{contact_id}/")
async def update_breach_contact(
    contact_id: str,
    payload: BreachContactsSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # 1️⃣ User
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 2️⃣ Encryption
        ce = getattr(request.app, "client_encryption", None) or init_encryption()
        request.app.client_encryption = ce

        dek_id = getattr(request.app, "dek_id", None) or ensure_data_key()
        request.app.dek_id = dek_id

        # 3️⃣ Validate ID
        try:
            dept_obj_id = ObjectId(contact_id)
            
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Breach Contact ID")

        # 4️⃣ Fetch block (Beanie-correct)
       
        breact_cont = await BrachResponseContactDocs.find_one(
            BrachResponseContactDocs.id == dept_obj_id,
            BrachResponseContactDocs.created_by.id == user.id,
            BrachResponseContactDocs.is_deleted == False,
        )
        

        

        if not breact_cont:
            raise HTTPException(status_code=404, detail="Breach Contact not found")

        # 5️⃣ Normalize name
        normalized_name = payload.name.strip().lower()
        normalized_phone = payload.phone.strip().lower()
        normalized_email = payload.email.strip().lower()

        # 6️⃣ Duplicate validation
        if normalized_name != BrachResponseContactDocs.name_search:
            duplicate = await BrachResponseContactDocs.find_one(
                And(
                    BrachResponseContactDocs.facility_id == breact_cont.facility_id,
                    BrachResponseContactDocs.name_search == normalized_name,
                    BrachResponseContactDocs.is_deleted == False,
                    BrachResponseContactDocs.id != breact_cont.id,
                    Or(
                        BrachResponseContactDocs.name_search == normalized_name,
                        BrachResponseContactDocs.phone_search == normalized_phone,
                    )
                )
            )

            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail="Breach Contact  with this name or phone already exists in this facility",
                )

        # 7️⃣ Encrypt & update
        encrypted = encrypt_dict(
            ce,
            dek_id,
            {
                "name": payload.name,
                "Role": payload.Role,
                "phone": payload.phone,
                "email": payload.email,
            }
        )

        breact_cont.name = encrypted["name"]
        breact_cont.Role = encrypted["Role"]
        breact_cont.phone = encrypted["phone"]
        breact_cont.email = encrypted["email"]
        breact_cont.name_search = normalized_name
        breact_cont.phone_search = normalized_phone
        breact_cont.email_search = normalized_email
        breact_cont.updated_at = datetime.now(timezone.utc)

        await breact_cont.save()

        # Audit log
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Update",
                resource="Facility Breach Contact",
                resource_id=str(breact_cont.id),
                status="success",
                notes="Breach Contact updated successfully",
            )
        except Exception:
            pass


        return {
            "success": True,
            "breach_conctact_id": str(breact_cont.id),
            "updated_at": breact_cont.updated_at,
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Crash:", e)
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Update",
                resource="Facility Breach Contact",
                resource_id=str(contact_id),
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error")

