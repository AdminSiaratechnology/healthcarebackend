# # app/clinicalmonitoring/api/patient_report.py

# from fastapi import APIRouter, HTTPException, Depends

# from app.clinicalmonitoring.schemas.patient_report import (
#     PatientReportCreateSchema,
#     PatientReportResponseSchema
# )

# from app.clinicalmonitoring.models.template_builder import TemplateBuilderDoc
# from app.clinicalmonitoring.models.subcategory import SubcategoryDoc
# from app.clinicalmonitoring.models.patient_report import PatientReportDoc

# from app.services.llm_service import build_prompt, call_llm


# router = APIRouter()


# @router.post("/create-report/", response_model=PatientReportResponseSchema)
# async def create_report(payload: PatientReportCreateSchema):

#     # 1️⃣ Get Template
#     template = await TemplateBuilderDoc.get(payload.template_id)
#     if not template:
#         raise HTTPException(status_code=404, detail="Template not found")

#     # 2️⃣ Get Subcategories
#     subcategories = await SubcategoryDoc.find(
#         SubcategoryDoc.id.in_([sub.id for sub in template.sub_category_ids])
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