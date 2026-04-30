# app/clinicalmonitoring/api/patient_report.py

from fastapi import APIRouter, HTTPException, Depends

from app.schemas.reports.report import (
    PatientReportCreateSchema,
    PatientReportResponseSchema
)

from app.clinicalmonitoring.models.template_builder import TemplateBuilderDoc
from app.clinicalmonitoring.models.subcategory import SubcategoryDoc
from app.reports.models import PatientReportDoc
from app.patients.models.patients import PatientDoc
from app.reports.llm_service import build_prompt, call_llm

from bson import ObjectId
from beanie.operators import In

router = APIRouter()


@router.post("/create-report/", response_model=PatientReportResponseSchema)
async def create_report(payload: PatientReportCreateSchema):

    # ✅ 1. Validate ObjectId format
    if not ObjectId.is_valid(payload.patient_id):
        raise HTTPException(400, "Invalid patient_id format")

    if not ObjectId.is_valid(payload.template_id):
        raise HTTPException(400, "Invalid template_id format")

    # ✅ 2. Convert
    patient_id = ObjectId(payload.patient_id)
    template_id = ObjectId(payload.template_id)

    # ✅ 3. Check existence
    template = await TemplateBuilderDoc.get(template_id)
    if not template:
        raise HTTPException(404, "Template not found")

    patient = await PatientDoc.get(patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")

    # 🔥 4. Subcategories fetch
    subcategories = await SubcategoryDoc.find(
        In(SubcategoryDoc.id, [sub.ref.id for sub in template.sub_category_ids])
    ).to_list()

    if not subcategories:
        raise HTTPException(400, "No subcategories found")

    # 🔥 5. Extract subcategory names
    subcat_names = [sub.name_search for sub in subcategories]

    # 🔥 6. Build prompt
    prompt = build_prompt(payload.text, subcat_names)

    # 🔥 7. CALL LLM (MAIN PART)
    llm_data = await call_llm(prompt)

    # 🔥 8. Safety: ensure all keys exist
    for name in subcat_names:
        llm_data.setdefault(name, "")

    # 🔥 9. Save to DB
    report = PatientReportDoc(
        patient_id=patient_id,
        template_id=template_id,
        data=llm_data,
        raw_text=payload.text
    )

    await report.insert()

    # 🔥 10. Response
    return {
        "message": "Report created successfully",
        "data": llm_data
    }

    # बाकी logic...

# @router.post("/create-report/", response_model=PatientReportResponseSchema)
# async def create_report(payload: PatientReportCreateSchema):

#     # 1️⃣ Get Template
#     template = await TemplateBuilderDoc.get(payload.template_id)
#     if not template:
#         raise HTTPException(status_code=404, detail="Template not found")

#     # 2️⃣ Get Subcategories
#     subcategories = await SubcategoryDoc.find(
#         In(SubcategoryDoc.id, [sub.ref.id for sub in template.sub_category_ids])
#     ).to_list()

#     if not subcategories:
#         raise HTTPException(status_code=400, detail="No subcategories found")

#     # 3️⃣ Extract names
#     subcat_names = [sub.name_search for sub in subcategories]

#     # 4️⃣ Build prompt
#     prompt = build_prompt(payload.text, subcat_names)

#     # 5️⃣ Call LLM
#     llm_data = await call_llm(prompt)

#     # 6️⃣ Ensure all keys exist
#     for name in subcat_names:
#         llm_data.setdefault(name, "")

#     # 7️⃣ Save
#     report = PatientReportDoc(
#         patient_id=payload.patient_id,
#         template_id=payload.template_id,
#         data=llm_data,
#         raw_text=payload.text
#     )

#     await report.insert()

#     return {
#         "message": "Report created successfully",
#         "data": llm_data
#     }