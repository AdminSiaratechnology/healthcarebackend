from datetime import  date, datetime, time, timedelta, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import ValidationError
from app.facility.models.facility import Facility

from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key, encrypt_value_deterministic,encrypt_dict
from app.auth.password import hash_password
from app.accounts.models.user import UserRole
from app.utils.audit import log_audit
from app.schemas.schedule.schedule import ScheduleSchema
from app.provider.models.providers import Provider
from app.VisitType.models import VisitType # Import VisitType
from beanie import PydanticObjectId, Link
from beanie.operators import In
import json
import os
from app.schedule.models.schedule import ScheduleDoc
from app.patients.models.patients import PatientDoc
from bson import ObjectId
from typing import Optional, List
from beanie.operators import And, Or, In, RegEx



router = APIRouter(prefix="/schedule", tags=["Schedule"])



# @router.post("/create/")
# async def create_schedule(
#     payload: ScheduleSchema,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:
#         # --------------------------------------------------
#         # 1️⃣ Current User Validation
#         # --------------------------------------------------
#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         # --------------------------------------------------
#         # 2️⃣ Encryption Init (Singleton Style)
#         # --------------------------------------------------
#         if not hasattr(request.app, "client_encryption"):
#             request.app.client_encryption = init_encryption()

#         if not hasattr(request.app, "dek_id"):
#             request.app.dek_id = ensure_data_key()

#         # --------------------------------------------------
#         # 3️⃣ Extract Payload Values (IMPORTANT: Before Use)
#         # --------------------------------------------------
#         selected_date = payload.selected_date.isoformat()
#         slot_time = payload.slot_time.strftime("%H:%M:%S")
       


#         # --------------------------------------------------
#         # 4️⃣ Facility Validation (Ownership Check)
#         # --------------------------------------------------
#         try:
#             facility_obj_id = ObjectId(payload.facility_id)
#         except Exception:
#             raise HTTPException(status_code=400, detail="Invalid facility_id")

#         facility = await Facility.find_one(
#             Facility.id == facility_obj_id,
#             Facility.created_by.id == user.id,
#         )

#         if not facility:
#             raise HTTPException(status_code=404, detail="Facility not found")

#         # --------------------------------------------------
#         # 5️⃣ Provider Validation
#         # --------------------------------------------------
#         try:
#             provider_obj_id = ObjectId(payload.provider_id)
#         except Exception:
#             raise HTTPException(status_code=400, detail="Invalid provider_id")

#         provider = await Provider.find_one(
#             Provider.id == provider_obj_id,
#             Provider.is_deleted == False,
#             Provider.status == "active",
#             fetch_links=True,
#         )

#         if not provider:
#             raise HTTPException(status_code=404, detail="Provider not found")

#         # Optional: Ensure provider belongs to facility
#         if provider.facility_ids:
#             provider_facility_ids = [str(f.id) for f in provider.facility_ids]
#             if str(facility.id) not in provider_facility_ids:
#                 raise HTTPException(
#                     status_code=400,
#                     detail="Provider does not belong to this facility",
#                 )

#         # --------------------------------------------------
#         # 6️⃣ Patient Validation
#         # --------------------------------------------------
#         try:
#             patient_obj_id = ObjectId(payload.patient_id)
#         except Exception:
#             raise HTTPException(status_code=400, detail="Invalid patient_id")

#         patient = await PatientDoc.find_one(
#             PatientDoc.id == patient_obj_id,
#             PatientDoc.is_deleted == False,
#             PatientDoc.status == "active",
#         )

#         if not patient:
#             raise HTTPException(status_code=404, detail="Patient not found")

#         # --------------------------------------------------
#         # 7️⃣ Duplicate Schedule Check
#         # (Matches your unique index)
#         # --------------------------------------------------
#         existing = await ScheduleDoc.find_one(
#             ScheduleDoc.provider_id.id == provider.id,
#             ScheduleDoc.schedule_date == selected_date,
#             ScheduleDoc.slot_time == slot_time,
#             ScheduleDoc.is_deleted == False,
#         )

#         if existing:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Schedule already exists for this provider at this time",
#             )

#         # --------------------------------------------------
#         # 8️⃣ Create Schedule Document
#         # --------------------------------------------------
#         schedule_doc = ScheduleDoc(
#             facility_id=facility,
#             provider_id=provider,
#             patient_id=patient,
#             created_by=user,
#             schedule_date=selected_date,
#             slot_time=slot_time,
            
#         )

#         await schedule_doc.insert()

#         # --------------------------------------------------
#         # 9️⃣ Success Response
#         # --------------------------------------------------
#         return {
#             "success": True,
#             "message": "Schedule created successfully",
#             "schedule_id": str(schedule_doc.id),
#             "facility_id": str(facility.id),
#             "provider_id": str(provider.id),
#             "patient_id": str(patient.id),
#         }

#     except HTTPException:
#         raise

#     except Exception as e:
#         print("❌ Schedule Create Crash:", e)
#         raise HTTPException(
#             status_code=500,
#             detail="Internal Server Error while creating schedule",
#         )





from datetime import datetime, timedelta, timezone





# @router.post("/create/")
# async def create_schedule(
#     payload: ScheduleSchema,
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),
# ):
#     try:

#         # --------------------------------------------------
#         # 1️⃣ User Validation
#         # --------------------------------------------------
#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         # --------------------------------------------------
#         # 2️⃣ Facility Validation
#         # --------------------------------------------------
#         try:
#             facility_obj_id = ObjectId(payload.facility_id)
#         except:
#             raise HTTPException(status_code=400, detail="Invalid facility_id")

#         facility = await Facility.get(facility_obj_id)
#         if not facility:
#             raise HTTPException(status_code=404, detail="Facility not found")

#         # --------------------------------------------------
#         # 3️⃣ Provider Validation
#         # --------------------------------------------------
#         try:
#             provider_obj_id = ObjectId(payload.provider_id)
#         except:
#             raise HTTPException(status_code=400, detail="Invalid provider_id")

#         provider = await Provider.find_one(
#             Provider.id == provider_obj_id,
#             Provider.is_deleted == False,
#             Provider.status == "active",
#         )

#         if not provider:
#             raise HTTPException(status_code=404, detail="Provider not found")

#         # --------------------------------------------------
#         # 4️⃣ Validate Patients
#         # --------------------------------------------------
#         patient_object_ids: List[ObjectId] = []
#         for pid in payload.patient_ids:
#             try:
#                 patient_object_ids.append(ObjectId(pid))
#             except:
#                 raise HTTPException(status_code=400, detail=f"Invalid patient_id: {pid}")

#         # patients = await PatientDoc.find(
#         #     PatientDoc.id.in_(patient_object_ids),
#         #     PatientDoc.is_deleted == False,
#         #     PatientDoc.status == "active",
#         # ).to_list()

#         patients = await PatientDoc.find(
#             {
#                 "_id": {"$in": patient_object_ids},
#                 "is_deleted": False,
#                 "status": "active",
#             }
#         ).to_list()
#         if len(patients) != len(patient_object_ids):
#             raise HTTPException(status_code=400, detail="One or more patients not found")

#         # --------------------------------------------------
#         # 5️⃣ Bulk Schedule Creation Logic
#         # --------------------------------------------------
#         start_datetime = payload.start_datetime.astimezone(timezone.utc)
#         slot_duration = int(payload.slot_duration_minutes)

#         created_schedules = []

#         for index, patient in enumerate(patients):

#             appointment_time = start_datetime + timedelta(
#                 minutes=slot_duration * index
#             )

#             # 🔴 Double Booking Check
#             existing = await ScheduleDoc.find_one(
#                 ScheduleDoc.provider_id.id == provider.id,
#                 ScheduleDoc.appointment_datetime == appointment_time,
#                 ScheduleDoc.is_deleted == False,
#             )

#             if existing:
#                 raise HTTPException(
#                     status_code=400,
#                     detail=f"Provider already booked at {appointment_time}",
#                 )

#             schedule_doc = ScheduleDoc(
#                 facility_id=facility,
#                 provider_id=provider,
#                 patient_id=patient,
#                 appointment_datetime=appointment_time,
#                 created_by=user,
#             )

#             await schedule_doc.insert()
#             created_schedules.append(str(schedule_doc.id))

#         # --------------------------------------------------
#         # 6️⃣ Success Response
#         # --------------------------------------------------
#         return {
#             "success": True,
#             "message": "Bulk schedule created successfully",
#             "total_created": len(created_schedules),
#             "schedule_ids": created_schedules,
#         }

#     except HTTPException:
#         raise

#     except Exception as e:
#         print("❌ Schedule Create Crash:", e)
#         raise HTTPException(
#             status_code=500,
#             detail="Internal Server Error while creating schedule",
#         )

@router.post("/create/")
async def create_schedule(
    payload: ScheduleSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:

        # --------------------------------------------------
        # 1️⃣ User Validation
        # --------------------------------------------------
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # --------------------------------------------------
        # 2️⃣ Facility Validation
        # --------------------------------------------------
        try:
            facility_obj_id = ObjectId(payload.facility_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid facility_id")

        facility = await Facility.get(facility_obj_id)
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        # --------------------------------------------------
        # 3️⃣ Provider Validation
        # --------------------------------------------------
        try:
            provider_obj_id = ObjectId(payload.provider_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid provider_id")

        provider = await Provider.find_one(
            Provider.id == provider_obj_id,
            Provider.is_deleted == False,
            Provider.status == "active",
        )

        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        # --------------------------------------------------
        # --------------------------------------------------
        # 4️⃣ VisitType Validation
        # --------------------------------------------------
        try:
            visit_type_obj_id = ObjectId(payload.visit_type_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid visit_type_id")

        visit_type = await VisitType.get(visit_type_obj_id)
        if not visit_type:
            raise HTTPException(status_code=404, detail="VisitType not found")

        # --------------------------------------------------
        # 5️⃣ Validate Patients
        # --------------------------------------------------
        patient_object_ids: List[ObjectId] = []

        for item in payload.patients:
            try:
                patient_object_ids.append(ObjectId(item.patient_id))
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid patient_id: {item.patient_id}",
                )

        patients = await PatientDoc.find(
            {
                "_id": {"$in": patient_object_ids},
                "is_deleted": False,
                "status": "active",
            }
        ).to_list()

        if len(patients) != len(patient_object_ids):
            raise HTTPException(
                status_code=400,
                detail="One or more patients not found or inactive",
            )

        # 🔥 Create mapping for fast lookup
        patient_map = {str(p.id): p for p in patients}

        # --------------------------------------------------
        # 5️⃣ Bulk Schedule Creation
        # --------------------------------------------------
        start_datetime = payload.start_datetime.astimezone(timezone.utc)
        slot_duration = int(payload.slot_duration_minutes)

        created_schedules = []

        for index, item in enumerate(payload.patients):

            patient = patient_map.get(item.patient_id)

            if not patient:
                raise HTTPException(
                    status_code=400,
                    detail=f"Patient not found: {item.patient_id}",
                )

            appointment_time = start_datetime + timedelta(
                minutes=slot_duration * index
            )

            # 🔴 Double Booking Check
            existing = await ScheduleDoc.find_one(
                {
                    "provider_id.$id": provider.id,
                    "appointment_datetime": appointment_time,
                    "is_deleted": False,
                }
            )

            if existing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Provider already booked at {appointment_time}",
                )

            schedule_doc = ScheduleDoc(
                facility_id=facility,
                provider_id=provider,
                patient_id=patient,
                visit_type=visit_type, # Add visit_type
                appointment_datetime=appointment_time,
                created_by=user,
                notes=item.notes,
            )

            await schedule_doc.insert()
            created_schedules.append(str(schedule_doc.id))

        # --------------------------------------------------
        # 6️⃣ Success Response
        # --------------------------------------------------
        return {
            "success": True,
            "message": "Bulk schedule created successfully",
            "total_created": len(created_schedules),
            "schedule_ids": created_schedules,
        }

    except HTTPException:
        raise

    except Exception as e:
        print("❌ Schedule Create Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while creating schedule",
        )


@router.put("/update/{schedule_id}/")
async def update_schedule(
    schedule_id: str,
    payload: ScheduleSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        # --------------------------------------------------
        # 1️⃣ Current User Validation
        # --------------------------------------------------
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # --------------------------------------------------
        # 2️⃣ Validate Schedule
        # --------------------------------------------------
        try:
            schedule_obj_id = ObjectId(schedule_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid schedule_id")

        schedule = await ScheduleDoc.find_one(
            ScheduleDoc.id == schedule_obj_id,
            ScheduleDoc.created_by.id == user.id,
            ScheduleDoc.is_deleted == False,
            fetch_links=True,
        )

        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        # --------------------------------------------------
        # 3️⃣ Facility Validation
        # --------------------------------------------------
        try:
            facility_obj_id = ObjectId(payload.facility_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid facility_id")

        facility = await Facility.get(facility_obj_id)
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

        # --------------------------------------------------
        # 4️⃣ Provider Validation
        # --------------------------------------------------
        try:
            provider_obj_id = ObjectId(payload.provider_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid provider_id")

        provider = await Provider.find_one(
            Provider.id == provider_obj_id,
            Provider.is_deleted == False,
            Provider.status == "active",
        )

        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        # --------------------------------------------------
        # 5️⃣ VisitType Validation
        # --------------------------------------------------
        try:
            visit_type_obj_id = ObjectId(payload.visit_type_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid visit_type_id")

        visit_type = await VisitType.get(visit_type_obj_id)
        if not visit_type:
            raise HTTPException(status_code=404, detail="VisitType not found")

        # --------------------------------------------------
        # 6️⃣ Patient Validation (Update specific schedule uses first patient in payload)
        # --------------------------------------------------
        if not payload.patients:
            raise HTTPException(status_code=400, detail="Patient information required")
        
        patient_item = payload.patients[0]
        try:
            patient_obj_id = ObjectId(patient_item.patient_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid patient_id")

        patient = await PatientDoc.find_one(
            PatientDoc.id == patient_obj_id,
            PatientDoc.is_deleted == False,
            PatientDoc.status == "active",
        )

        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        # --------------------------------------------------
        # 6️⃣ Double Booking Check (Ignore current schedule)
        # --------------------------------------------------
        appointment_time = payload.start_datetime.astimezone(timezone.utc)
        
        duplicate = await ScheduleDoc.find_one(
            {
                "_id": {"$ne": schedule.id},
                "provider_id.$id": provider.id,
                "appointment_datetime": appointment_time,
                "is_deleted": False,
            }
        )

        if duplicate:
            raise HTTPException(
                status_code=400,
                detail=f"Provider already booked at {appointment_time}",
            )

        # --------------------------------------------------
        # 7️⃣ Update Schedule
        # --------------------------------------------------
        schedule.facility_id = facility
        schedule.provider_id = provider
        schedule.patient_id = patient
        schedule.visit_type = visit_type # Update visit_type
        schedule.appointment_datetime = payload.start_datetime.astimezone(timezone.utc)
        schedule.notes = patient_item.notes
        schedule.updated_at = datetime.now(timezone.utc)
        await schedule.save()

        return {
            "success": True,
            "message": "Schedule updated successfully",
            "schedule_id": str(schedule.id),
            "facility_id": str(facility.id),
            "provider_id": str(provider.id),
            "patient_id": str(patient.id),
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Schedule Update Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating schedule",
        )

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Schedule Update Crash:", e)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while updating schedule",
        )






# @router.get("/list/")
# async def list_schedules(
#     request: Request,
#     current_user_id: str = Depends(get_current_user_id),

#     page: int = Query(1, ge=1),
#     page_size: int = Query(10, ge=1, le=100),

#     from_date: Optional[date] = Query(None, description="Filter start date (YYYY-MM-DD)"),
#     to_date: Optional[date] = Query(None, description="Filter end date (YYYY-MM-DD)"),

#     facility_ids: Optional[List[str]] = Query(None),
#     provider_ids: Optional[List[str]] = Query(None),

#     search: Optional[str] = Query(None),
#     status: Optional[str] = Query(None),
# ):
#     try:
#         user = await UserDoc.get(current_user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         conditions = [
#             ScheduleDoc.created_by.id == user.id,
#             ScheduleDoc.is_deleted == False,
#         ]

#         if status:
#             conditions.append(ScheduleDoc.status == status.lower())

#         # Facility filter
#         if facility_ids:
#             try:
#                 facility_object_ids = [ObjectId(fid) for fid in facility_ids]
#                 conditions.append(In(ScheduleDoc.facility_id.id, facility_object_ids))
#             except Exception as exc:
#                 raise HTTPException(status_code=400, detail=f"Invalid facility_ids: {exc}")

#         # Provider filter
#         if provider_ids:
#             try:
#                 provider_object_ids = [ObjectId(pid) for pid in provider_ids]
#                 conditions.append(In(ScheduleDoc.provider_id.id, provider_object_ids))
#             except Exception as exc:
#                 raise HTTPException(status_code=400, detail=f"Invalid provider_ids: {exc}")

#         # Search filter
#         if search:
#             search_value = search.lower().strip()
#             conditions.append(
#                 Or(
#                     RegEx(
#                         ScheduleDoc.facility_id.facility_name_search,
#                         f"^{search_value}",
#                         options="i"
#                     ),
#                     RegEx(
#                         ScheduleDoc.provider_id.user.full_name_search,
#                         f"^{search_value}",
#                         options="i"
#                     ),
#                 )
#             )

#         # Date range filter – compare as ISO strings
#         if from_date:
#             conditions.append(ScheduleDoc.schedule_date >= from_date.isoformat())
#         if to_date:
#             conditions.append(ScheduleDoc.schedule_date <= to_date.isoformat())

#         # Query with fetch_links
#         query = ScheduleDoc.find(*conditions, fetch_links=True).sort("-created_at")

#         total = await query.count()

#         skip = (page - 1) * page_size
#         schedules = await query.skip(skip).limit(page_size).to_list()

#         # Response building
#         result = []
#         for schedule in schedules:
#             provider = getattr(schedule, "provider_id", None)
#             facility = getattr(schedule, "facility_id", None)

#             result.append({
#                 "id": str(schedule.id),
#                 "provider_id": str(provider.id) if provider else None,
#                 "provider_name": (
#                     provider.user.full_name_search
#                     if provider and hasattr(provider.user, "full_name_search") else None
#                 ),
#                 "facility_id": str(facility.id) if facility else None,
#                 "facility_name": (
#                     facility.facility_name_search
#                     if facility and hasattr(facility, "facility_name_search") else None
#                 ),
#                 "date": schedule.schedule_date,
#                 "slot_time": schedule.slot_time,
#                 "status": schedule.status,
#                 "created_at": schedule.created_at.isoformat() if schedule.created_at else None,
#                 "updated_at": schedule.updated_at.isoformat() if schedule.updated_at else None,
#             })

#         # Optional audit log (comment out if not needed)
#         # await log_audit(...)

#         return {
#             "success": True,
#             "page": page,
#             "page_size": page_size,
#             "total": total,
#             "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 1,
#             "count": len(result),
#             "data": result,
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         print("❌ List Schedules Error:", str(e))
#         raise HTTPException(status_code=500, detail="Internal Server Error")





@router.get("/list/")
async def list_schedules(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),

    facility_ids: Optional[List[str]] = Query(None),
    provider_ids: Optional[List[str]] = Query(None),

    status: Optional[str] = Query(None),
):
    try:
        # --------------------------------------------------
        # 1️⃣ User Validation
        # --------------------------------------------------
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # --------------------------------------------------
        # 2️⃣ Encryption Init
        # --------------------------------------------------
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce

        # --------------------------------------------------
        # 3️⃣ Build Conditions (Beanie Style)
        # --------------------------------------------------
        conditions = [
            ScheduleDoc.created_by.id == user.id,
            ScheduleDoc.is_deleted == False,
        ]

        if status:
            conditions.append(
                ScheduleDoc.status == status.lower()
            )

        # Facility Filter
        if facility_ids:
            try:
                facility_object_ids = [ObjectId(fid) for fid in facility_ids]
                conditions.append(
                    ScheduleDoc.facility_id.id.in_(facility_object_ids)
                )
            except:
                raise HTTPException(status_code=400, detail="Invalid facility_ids")

        # Provider Filter
        if provider_ids:
            try:
                provider_object_ids = [ObjectId(pid) for pid in provider_ids]
                conditions.append(
                    ScheduleDoc.provider_id.id.in_(provider_object_ids)
                )
            except:
                raise HTTPException(status_code=400, detail="Invalid provider_ids")

        # Date Range Filter
        if from_date:
            from_datetime = datetime.combine(
                from_date, time.min
            ).replace(tzinfo=timezone.utc)

            conditions.append(
                ScheduleDoc.appointment_datetime >= from_datetime
            )

        if to_date:
            to_datetime = datetime.combine(
                to_date, time.max
            ).replace(tzinfo=timezone.utc)

            conditions.append(
                ScheduleDoc.appointment_datetime <= to_datetime
            )

        # --------------------------------------------------
        # 4️⃣ Query Execution
        # --------------------------------------------------
        query = ScheduleDoc.find(
            *conditions,
            fetch_links=True
        ).sort("-appointment_datetime")

        total = await query.count()

        skip = (page - 1) * page_size
        schedules = await query.skip(skip).limit(page_size).to_list()

        # --------------------------------------------------
        # 5️⃣ Response Build
        # --------------------------------------------------
        result = []

        def _dec_json(binval):
            try:
                if not binval:
                    return None
                s = decrypt_value(ce, binval)
                try:
                    return json.loads(s) if isinstance(s, str) else s
                except:
                    return s
            except:
                return None

        for schedule in schedules:
            provider = schedule.provider_id
            facility = schedule.facility_id
            patient = schedule.patient_id

            # Fetch nested links if needed
            if provider and isinstance(provider.user, Link):
                await provider.fetch_link("user")
            
            if patient and isinstance(patient.user_id, Link):
                await patient.fetch_link("user_id")

            # Decrypt patient details if needed
            patient_details = None
            if patient:
                patient_details = {
                    "personal_information": _dec_json(patient.personal_information),
                    "admission_information": _dec_json(patient.admisson_information),
                    "address_information": _dec_json(patient.address_information),
                    "insurance_information": _dec_json(patient.insurance_information),
                    "emergency_contact_information": _dec_json(patient.emergency_contact_information),
                    "diagnosis_information": _dec_json(patient.diagnosis),
                }

            result.append({
                "id": str(schedule.id),

                "facility_id": str(facility.id) if facility else None,
                "facility_name": getattr(facility, "facility_name_search", None),

                "provider_id": str(provider.id) if provider else None,
                "provider_name": (
                    provider.user.full_name_search
                    if provider and provider.user else None
                ),

                # "patient_id": str(patient.id) if patient else None,
                # "patient_name": (
                #     patient.user_id.full_name_search
                #     if patient and patient.user_id else None
                # ),
                "patient_details": patient_details,

                "appointment_datetime": (
                    schedule.appointment_datetime.isoformat()
                    if schedule.appointment_datetime else None
                ),

                "status": schedule.status,
                "notes": schedule.notes,

                "created_at": (
                    schedule.created_at.isoformat()
                    if schedule.created_at else None
                ),
            })
        

        return {
            "success": True,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
            "count": len(result),
            "data": result,
        }

    except HTTPException:
        raise

    except Exception as e:
        print("❌ List Schedules Error:", str(e))
        raise HTTPException(status_code=500, detail="Internal Server Error")