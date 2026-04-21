from fastapi import APIRouter, HTTPException, Depends, status, Query
from beanie import PydanticObjectId
from beanie.operators import RegEx
from typing import Optional
from datetime import datetime, timezone

from app.VisitType.models import VisitType
from app.schemas.VisitType.visit_type import VisitTypeCreate, VisitTypeUpdate, VisitTypeResponse, PaginatedVisitTypeResponse
from app.auth.deps import get_current_user_id
from app.accounts.models.user import UserDoc

router = APIRouter(prefix="/visit-type", tags=["VisitType"])


@router.post("/", response_model=VisitTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_visit_type(
    payload: VisitTypeCreate,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Create a new Visit Type.
    """
    user = await UserDoc.get(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    existing = await VisitType.find_one(
        VisitType.name == payload.name,
        VisitType.is_deleted == False
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Visit type '{payload.name}' already exists"
        )

    visit_type = VisitType(
        name=payload.name,
        created_by=user
    )
    await visit_type.insert()
    return visit_type


@router.get("/", response_model=PaginatedVisitTypeResponse)
async def list_visit_types(
    current_user_id: str = Depends(get_current_user_id),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None)
):
    """
    List all visit types with pagination and search.
    """
    conditions = [VisitType.is_deleted == False]

    if search:
        conditions.append(RegEx(VisitType.name, f".*{search}.*", "i"))

    total = await VisitType.find(*conditions).count()

    skip_count = (page - 1) * limit
    visit_types = await VisitType.find(*conditions).skip(skip_count).limit(limit).to_list()

    return PaginatedVisitTypeResponse(
        total=total,
        page=page,
        limit=limit,
        items=visit_types
    )


@router.get("/{id}", response_model=VisitTypeResponse)
async def get_visit_type(
    id: PydanticObjectId,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Get a specific visit type by ID.
    """
    visit_type = await VisitType.get(id)
    if not visit_type or visit_type.is_deleted:
        raise HTTPException(status_code=404, detail="Visit type not found")
    return visit_type


@router.patch("/{id}", response_model=VisitTypeResponse)
async def update_visit_type(
    id: PydanticObjectId,
    payload: VisitTypeUpdate,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Update a visit type.
    """
    visit_type = await VisitType.get(id)
    if not visit_type or visit_type.is_deleted:
        raise HTTPException(status_code=404, detail="Visit type not found")

    update_data = payload.model_dump(exclude_unset=True)

    if "name" in update_data:
        existing = await VisitType.find_one(
            VisitType.name == update_data["name"],
            VisitType.id != id,
            VisitType.is_deleted == False
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Visit type '{update_data['name']}' already exists"
            )

    for key, value in update_data.items():
        setattr(visit_type, key, value)

    visit_type.updated_at = datetime.now(timezone.utc)
    await visit_type.save()
    return visit_type


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_visit_type(
    id: PydanticObjectId,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Soft delete a visit type.
    """
    visit_type = await VisitType.get(id)
    if not visit_type or visit_type.is_deleted:
        raise HTTPException(status_code=404, detail="Visit type not found")

    user = await UserDoc.get(current_user_id)

    visit_type.is_deleted = True
    visit_type.deleted_at = datetime.now(timezone.utc)
    visit_type.deleted_by = user
    await visit_type.save()
    return None
