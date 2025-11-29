from fastapi import APIRouter, Request, HTTPException
from app.schemas.patient import Patient
from app.accounts.models.patient import PatientDoc
from app.utils.audit import log_audit
from app.encryption.encryption import encrypt_value,decrypt_value   # <-- IMPORTANT

router = APIRouter()

@router.post("/patient")
async def test_encrypt(patient: Patient, request: Request):
    try:
        client_encryption = request.app.client_encryption
        dek_id = request.app.dek_id

        encrypted_doc = {
            "name": patient.name,
            "ssn": encrypt_value(client_encryption, dek_id, patient.ssn),
            "phone": encrypt_value(client_encryption, dek_id, patient.phone)
        }

        doc = PatientDoc(**encrypted_doc)
        await doc.insert()

        await log_audit(
            request=request,
            action="CREATE",
            resource="patient",
            resource_id=str(doc.id),
            status="success",
            notes="Patient encrypted data inserted"
        )

        return {
            "inserted_id": str(doc.id),
            "message": "Encrypted data saved successfully!"
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


@router.get("/patients")
async def get_all_patients(request: Request):
    client_encryption = request.app.client_encryption

    docs = await PatientDoc.find_all().to_list()

    if not docs:
        return {"patients": []}

    decrypted_list = []

    for doc in docs:
        decrypted_list.append({
            "id": str(doc.id),
            "name": doc.name,
            "ssn": decrypt_value(client_encryption, doc.ssn),
            "phone": decrypt_value(client_encryption, doc.phone)
        })

    return {"patients": decrypted_list}
