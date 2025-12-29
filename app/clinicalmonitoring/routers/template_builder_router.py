from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import ValidationError
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key, encrypt_value_deterministic
from app.utils.audit import log_audit
from app.schemas.clinicalmonitoring.template_builder import TemplateBuilderSchema
from beanie import PydanticObjectId
import json
import os
from app.clinicalmonitoring.models.subcategory import SubcategoryDoc
from app.clinicalmonitoring.models.template_builder import TemplateBuilderDoc
from app.clinicalmonitoring.models.template_builder import TemplateBuilderDoc
from app.clinicalmonitoring.models.category import CategoryDoc
from app.patients.models.patients import PatientDoc
from app.provider.models.providers import Provider


router = APIRouter(prefix="/templatebuilder", tags=["TemplateBuilder"])


def _dec_str(client_encryption, encrypted_val):
    if not encrypted_val:
        return None
    raw = decrypt_value(client_encryption, encrypted_val)
    return raw.decode() if isinstance(raw, (bytes, bytearray)) else raw

@router.post("/create/{subcategory_id}/")
async def create_template(
    payload: TemplateBuilderSchema,
    request: Request,
    subcategory_id: str,
    patient_id: str | None = None,
    provider_id: str | None = None,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce
        dek_id = getattr(request.app, "dek_id", None)
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        try:
            subcat = await SubcategoryDoc.get(PydanticObjectId(subcategory_id))
        except Exception:
            subcat = None
        if not subcat:
            raise HTTPException(status_code=404, detail="Subcategory not found")
        print("usersssss role",user.role)

        patient_obj = None
        if patient_id:
            try:
                p_oid = PydanticObjectId(patient_id)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid patient_id")
            patient_obj = await PatientDoc.get(p_oid)
            if not patient_obj:
                raise HTTPException(status_code=404, detail="Patient not found")

        provider_obj = None
        if provider_id:
            try:
                prov_oid = PydanticObjectId(provider_id)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid provider_id")
            provider_obj = await Provider.get(prov_oid)
            if not provider_obj:
                raise HTTPException(status_code=404, detail="Provider not found")
        enc_name_det = encrypt_value_deterministic(ce, dek_id, payload.template_name)
        existing = await TemplateBuilderDoc.find_one({"sub_category_id.$id": subcat.id, "template_name": enc_name_det})
        if not existing:
            templates = await TemplateBuilderDoc.find({"sub_category_id.$id": subcat.id}).to_list()
            for t in templates:
                if _dec_str(ce, t.template_name) == payload.template_name:
                    existing = t
                    break
        if existing:
            return {"message": "Template already exists", "id": str(existing.id)}

        enc_short = encrypt_value(ce, dek_id, payload.short_name) if payload.short_name else None
        enc_disc = encrypt_value(ce, dek_id, payload.discipline) if payload.discipline else None

        doc = TemplateBuilderDoc(
            sub_category_id=subcat,
            patient_id=patient_obj,
            provider_id=provider_obj,
            template_name=enc_name_det,
            short_name=enc_short,
            discipline=enc_disc,
            created_by=user,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await doc.insert()

        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Create",
                resource="TemplateBuilder",
                resource_id=str(doc.id),
                status="success",
                notes="Template created",
            )
        except Exception:
            pass

        return {"id": str(doc.id)}
    except HTTPException:
        raise
    except Exception as e:
        try:
            await log_audit(
                request=request,
                user_id=str(current_user_id),
                action="Create",
                resource="TemplateBuilder",
                resource_id="N/A",
                status="failed",
                notes=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal Server Error while creating template")


# @router.get("/list")
# async def list_templates(
#     request: Request,
#     q: str | None = None,
#     page: int = 1,
#     page_size: int = 10,
#     subcategory_id: str | None = None,
#     category_id: str | None = None,
#     patient_id: str | None = None,
#     provider_id: str | None = None,
#     current_user_id: str = Depends(get_current_user_id)
# ):
#     ce = getattr(request.app, "client_encryption", None)
#     if ce is None:
#         ce = init_encryption()
#         request.app.client_encryption = ce

#     user = await UserDoc.get(current_user_id)
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     base_query = {}
#     if subcategory_id:
#         try:
#             subcat_doc = await SubcategoryDoc.get(PydanticObjectId(subcategory_id))
#         except Exception:
#             subcat_doc = None
#         if not subcat_doc:
#             raise HTTPException(status_code=404, detail="Subcategory not found")
#         base_query = {"sub_category_id.$id": subcat_doc.id}
#     elif category_id:
#         try:
#             cat_oid = PydanticObjectId(category_id)
#         except Exception:
#             raise HTTPException(status_code=400, detail="Invalid category_id")
#         subcats = await SubcategoryDoc.find({"category_id.$id": cat_oid}).to_list()
#         subcat_ids = [sc.id for sc in subcats]
#         base_query = {"sub_category_id.$id": {"$in": subcat_ids}} if subcat_ids else {"sub_category_id.$id": {"$in": []}}

#     if patient_id:
#         try:
#             p_oid = PydanticObjectId(patient_id)
#         except Exception:
#             raise HTTPException(status_code=400, detail="Invalid patient_id")
#         base_query["patient_id.$id"] = p_oid

#     if provider_id:
#         try:
#             prov_oid = PydanticObjectId(provider_id)
#         except Exception:
#             raise HTTPException(status_code=400, detail="Invalid provider_id")
#         base_query["provider_id.$id"] = prov_oid

    
#     all_docs = await TemplateBuilderDoc.find(base_query).sort(-TemplateBuilderDoc.created_at).to_list()

#     def matches(item_name: str | None, needle: str) -> bool:
#         return item_name is not None and needle.lower() in item_name.lower()

#     items = []
#     for t in all_docs:
#         name = _dec_str(ce, t.template_name)
#         short = _dec_str(ce, t.short_name)
#         disc = _dec_str(ce, t.discipline)

#         # fetch subcategory name
#         sc_name = None
#         sc_id_str = None
#         try:
#             sc_id = t.sub_category_id.id if hasattr(t.sub_category_id, "id") else t.sub_category_id
#             sc = await SubcategoryDoc.get(sc_id)
#             if sc:
#                 sc_name = _dec_str(ce, sc.name)
#                 sc_id_str = str(sc.id)
#         except Exception:
#             pass

#         if q:
#             if not (
#                 matches(name, q) or matches(sc_name, q) or matches(disc, q)
#             ):
#                 continue

#         p_id_str = None
#         try:
#             p_id = None
#             if hasattr(t.patient_id, "id"):
#                 p_id = t.patient_id.id
#             elif hasattr(getattr(t.patient_id, "ref", None), "id"):
#                 p_id = t.patient_id.ref.id
#             elif t.patient_id:
#                 p_id = t.patient_id
#             p_id_str = str(p_id) if p_id is not None else None
#         except Exception:
#             pass

#         prov_id_str = None
#         try:
#             pr_id = None
#             if hasattr(t.provider_id, "id"):
#                 pr_id = t.provider_id.id
#             elif hasattr(getattr(t.provider_id, "ref", None), "id"):
#                 pr_id = t.provider_id.ref.id
#             elif t.provider_id:
#                 pr_id = t.provider_id
#             prov_id_str = str(pr_id) if pr_id is not None else None
#         except Exception:
#             pass

#         items.append({
#             "id": str(t.id),
#             "template_name": name,
#             "short_name": short,
#             "discipline": disc,
#             "subcategory_id": sc_id_str,
#             "subcategory_name": sc_name,
#             "patient_id": p_id_str,
#             "provider_id": prov_id_str,
#             "created_at": t.created_at,
#             "updated_at": t.updated_at,
#         })

#     total = len(items)
#     start = max((page - 1) * page_size, 0)
#     end = start + page_size
#     paged = items[start:end]

#     try:
#         await log_audit(
#             request=request,
#             user_id=str(user.id),
#             action="Read",
#             resource="TemplateBuilder",
#             resource_id="list",
#             status="success",
#             notes="Templates listed",
#         )
#     except Exception:
#         pass

#     return {
#         "data": paged,
#         "meta": {
#             "total": total,
#             "page": page,
#             "page_size": page_size,
#             "pages": (total + page_size - 1) // page_size,
#         }
#     }


@router.get("/list")
async def list_templates(
    request: Request,
    q: str | None = None,
    page: int = 1,
    page_size: int = 10,
    subcategory_id: str | None = None,
    category_id: str | None = None,
    patient_id: str | None = None,
    provider_id: str | None = None,
    current_user_id: str = Depends(get_current_user_id)
):
    # ---------------- Encryption ----------------
    ce = getattr(request.app, "client_encryption", None)
    if ce is None:
        ce = init_encryption()
        request.app.client_encryption = ce

    # ---------------- User ----------------
    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ---------------- Base Query ----------------
    base_query: dict = {}

    # 🔒 IMPORTANT: only user-created templates
    base_query["created_by.$id"] = user.id

    # ---------------- Subcategory filter ----------------
    if subcategory_id:
        try:
            subcat_doc = await SubcategoryDoc.get(PydanticObjectId(subcategory_id))
        except Exception:
            subcat_doc = None

        if not subcat_doc:
            raise HTTPException(status_code=404, detail="Subcategory not found")

        base_query["sub_category_id.$id"] = subcat_doc.id

    # ---------------- Category filter ----------------
    elif category_id:
        try:
            cat_oid = PydanticObjectId(category_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid category_id")

        subcats = await SubcategoryDoc.find(
            {"category_id.$id": cat_oid}
        ).to_list()

        subcat_ids = [sc.id for sc in subcats]
        base_query["sub_category_id.$id"] = {"$in": subcat_ids} if subcat_ids else {"$in": []}

    # ---------------- Patient filter ----------------
    if patient_id:
        try:
            p_oid = PydanticObjectId(patient_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid patient_id")

        base_query["patient_id.$id"] = p_oid

    # ---------------- Provider filter ----------------
    if provider_id:
        try:
            prov_oid = PydanticObjectId(provider_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid provider_id")

        base_query["provider_id.$id"] = prov_oid

    # ---------------- Fetch data ----------------
    all_docs = await TemplateBuilderDoc.find(
        base_query
    ).sort(-TemplateBuilderDoc.created_at).to_list()

    # ---------------- Search helper ----------------
    def matches(item_name: str | None, needle: str) -> bool:
        return item_name is not None and needle.lower() in item_name.lower()

    # ---------------- Build response ----------------
    items = []

    for t in all_docs:
        name = _dec_str(ce, t.template_name)
        short = _dec_str(ce, t.short_name)
        disc = _dec_str(ce, t.discipline)

        # ---- Subcategory info ----
        sc_name = None
        sc_id_str = None
        try:
            sc_id = t.sub_category_id.id if hasattr(t.sub_category_id, "id") else t.sub_category_id
            sc = await SubcategoryDoc.get(sc_id)
            if sc:
                sc_name = _dec_str(ce, sc.name)
                sc_id_str = str(sc.id)
        except Exception:
            pass

        # ---- Search filter ----
        if q:
            if not (
                matches(name, q) or
                matches(sc_name, q) or
                matches(disc, q)
            ):
                continue

        # ---- Patient ID ----
        p_id_str = None
        try:
            if hasattr(t.patient_id, "id"):
                p_id_str = str(t.patient_id.id)
            elif t.patient_id:
                p_id_str = str(t.patient_id)
        except Exception:
            pass

        # ---- Provider ID ----
        prov_id_str = None
        try:
            if hasattr(t.provider_id, "id"):
                prov_id_str = str(t.provider_id.id)
            elif t.provider_id:
                prov_id_str = str(t.provider_id)
        except Exception:
            pass

        items.append({
            "id": str(t.id),
            "template_name": name,
            "short_name": short,
            "discipline": disc,
            "subcategory_id": sc_id_str,
            "subcategory_name": sc_name,
            "patient_id": p_id_str,
            "provider_id": prov_id_str,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        })

    # ---------------- Pagination ----------------
    total = len(items)
    start = max((page - 1) * page_size, 0)
    end = start + page_size
    paged = items[start:end]

    # ---------------- Audit log ----------------
    try:
        await log_audit(
            request=request,
            user_id=str(user.id),
            action="Read",
            resource="TemplateBuilder",
            resource_id="list",
            status="success",
            notes="User templates listed",
        )
    except Exception:
        pass

    # ---------------- Response ----------------
    return {
        "data": paged,
        "meta": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        }
    }
