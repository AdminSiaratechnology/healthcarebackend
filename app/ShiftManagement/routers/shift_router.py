from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request,Query
from app.accounts.models import user
from app.clinicalmonitoring.models.category import CategoryDoc
from app.facility.models.facility import Facility
from app.accounts.models.user import UserDoc
from app.auth.deps import get_current_user_id
from app.encryption.encryption import encrypt_value, decrypt_value, init_encryption, ensure_data_key
from app.utils.audit import log_audit
from app.schemas.ShiftManagement.shift import ShiftManagementSchema
from beanie import PydanticObjectId
from app.ShiftManagement.models.shift import ShiftManagementDocs

router = APIRouter(prefix="/shift_management", tags=["Shift Management"])



@router.post("/create/shift/")
async def create_shift(
    shift: ShiftManagementSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce
        dek_id = ensure_data_key()
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user = await UserDoc.get(current_user_id)
       
        
        facility_obj_ids = []
        for fid in shift.facility_ids:
            try:
                facility_obj_id = PydanticObjectId(fid)
                facility = await Facility.get(facility_obj_id)
                if not facility:
                    raise HTTPException(status_code=404, detail=f"Facility with ID {fid} not found")
                facility_obj_ids.append(facility)
            except Exception:
                raise HTTPException(status_code=400, detail=f"Invalid Facility ID format: {fid}")

        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        shift_doc = ShiftManagementDocs(
            name=encrypt_value(ce, dek_id, shift.name),
            shift=encrypt_value(ce, dek_id, shift.shift),
            start_time=encrypt_value(ce, dek_id, shift.start_time),
            end_time=encrypt_value(ce, dek_id, shift.end_time),
            shift_type=encrypt_value(ce, dek_id, shift.shift_type),
            break_duration=encrypt_value(ce, dek_id, shift.break_duration),
            minumum_staff_required=encrypt_value(ce, dek_id, shift.minumum_staff_required),
            maximum_staff_allowed=encrypt_value(ce, dek_id, shift.maximum_staff_allowed),
            priority=encrypt_value(ce, dek_id, shift.priority),
            required_role=encrypt_value(ce, dek_id, shift.required_role),
            active_days=encrypt_value(ce, dek_id, shift.active_days),
            description=encrypt_value(ce, dek_id, shift.description),
            facility_ids=facility_obj_ids,
            created_by=user,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )


        await shift_doc.insert()    
        await log_audit(
            user_id=str(user.id),
            request=request,
            action="Create",
            resource="ShiftManagement",
            resource_id=str(shift_doc.id),
            status="success",
            notes=f"Shift {shift.name} created successfully."
        )
        return {
            "success": True,
            "shift_id": str(shift_doc.id),
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        await log_audit(
            user_id=current_user_id,
            request=request,
            action="Create",
            resource="ShiftManagement",
            resource_id="N/A",
            status="failure",
            notes=str(e)
        )
        raise HTTPException(status_code=500, detail="Internal Server Error")
    

@router.get("/shits/list/")
async def list_shifts(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1),
    search: str | None = Query(None, description="Search by shift name")
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce
        dek_id = ensure_data_key()
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        # shifts = await ShiftManagementDocs.find({}).to_list()
        shifts = await ShiftManagementDocs.find(
            ShiftManagementDocs.created_by.id == user.id
        ).sort("-created_at").to_list()
        result = []
        search_lower = search.lower() if search else None
        
        for shift in shifts:
            if search_lower:
                name_dec = _dec_str(ce, shift.name)
                if not name_dec or search_lower not in name_dec.lower():
                    continue
            result.append({
                "id": str(shift.id),
                "name": _dec_str(ce, shift.name),
                "shift": _dec_str(ce, shift.shift),
                "start_time": _dec_str(ce, shift.start_time),
                "end_time": _dec_str(ce, shift.end_time),
                "shift_type": _dec_str(ce, shift.shift_type),
                "break_duration": _dec_str(ce, shift.break_duration),
                "minumum_staff_required": _dec_str(ce, shift.minumum_staff_required),
                "maximum_staff_allowed": _dec_str(ce, shift.maximum_staff_allowed),
                "priority": _dec_str(ce, shift.priority),
                "required_role": _dec_str(ce, shift.required_role),
                "active_days": _dec_str(ce, shift.active_days),
                "description": _dec_str(ce, shift.description),
                "facility_ids": [str(facility.ref.id) for facility in shift.facility_ids],
                "created_at": shift.created_at,
                "updated_at": shift.updated_at,
            })
        total = len(result)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_docs = result[start:end]
        try:
            await log_audit(
                request=request,
                user_id=str(user.id),
                action="Read",
                resource="ShiftManagement",
                resource_id="N/A",
                status="success",
                notes="Shifts listed successfully",
            ) 
        except Exception:
            pass  
        return {
        "items": paginated_docs,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": (total + page_size - 1) // page_size,
        }
    }
    except Exception as e:
        print("error is here.......",e)
        raise HTTPException(status_code=500, detail="Internal Server Error while listing shifts"
)
    


@router.put("/update/shift/{shift_id}/")
async def update_shift(
    shift_id: str,
    shift: ShiftManagementSchema,
    request: Request,
    current_user_id: str = Depends(get_current_user_id)
):
    try:
        ce = getattr(request.app, "client_encryption", None)
        if ce is None:
            ce = init_encryption()
            request.app.client_encryption = ce
        dek_id = ensure_data_key()
        if dek_id is None:
            dek_id = ensure_data_key()
            request.app.dek_id = dek_id
        user = await UserDoc.get(current_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        shift_doc = await ShiftManagementDocs.get(PydanticObjectId(shift_id))
        if not shift_doc:
            raise HTTPException(status_code=404, detail="Shift not found")
        facility_obj_ids = []
        for fid in shift.facility_ids:
            try:
                facility_obj_id = PydanticObjectId(fid)
                facility = await Facility.get(facility_obj_id)
                if not facility:
                    raise HTTPException(status_code=404, detail=f"Facility with ID {fid} not found")
                facility_obj_ids.append(facility)
            except Exception:
                raise HTTPException(status_code=400, detail=f"Invalid Facility ID format: {fid}")
        shift_doc.name = encrypt_value(ce, dek_id, shift.name)
        shift_doc.shift = encrypt_value(ce, dek_id, shift.shift)
        shift_doc.start_time = encrypt_value(ce, dek_id, shift.start_time)
        shift_doc.end_time = encrypt_value(ce, dek_id, shift.end_time)
        shift_doc.shift_type = encrypt_value(ce, dek_id, shift.shift_type)
        shift_doc.break_duration = encrypt_value(ce, dek_id, shift.break_duration)
        shift_doc.minumum_staff_required = encrypt_value(ce, dek_id, shift.minumum_staff_required)
        shift_doc.maximum_staff_allowed = encrypt_value(ce, dek_id, shift.maximum_staff_allowed)
        shift_doc.priority = encrypt_value(ce, dek_id, shift.priority)
        shift_doc.required_role = encrypt_value(ce, dek_id, shift.required_role)
        shift_doc.active_days = encrypt_value(ce, dek_id, shift.active_days)
        shift_doc.description = encrypt_value(ce, dek_id, shift.description)
        shift_doc.facility_ids = facility_obj_ids
        shift_doc.updated_at =  datetime.now()
        await shift_doc.save()
        await log_audit(
            user_id=str(user.id),
            request=request,
            action="Update",
            resource="ShiftManagement",
            resource_id=str(shift_doc.id),
            status="success",
            notes=f"Shift {shift.name} updated successfully."
        )   
    
        return {
            "success": True,
            "shift_id": str(shift_doc.id),
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        await log_audit(
            user_id=current_user_id,
            request=request,
            action="Update",
            resource="ShiftManagement",
            resource_id=shift_id,
            status="failure",
            notes=str(e)
        )
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
