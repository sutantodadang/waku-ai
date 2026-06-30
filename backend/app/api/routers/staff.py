from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_business
from app.models import Business, Staff
from app.schemas import StaffCreate, StaffResponse

router = APIRouter()


@router.get("/api/staff", response_model=list[StaffResponse])
async def list_staff(
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    rows = (await session.execute(
        select(Staff).where(Staff.business_id == business.id, Staff.active == True)  # noqa: E712
    )).scalars().all()
    return list(rows)


@router.post("/api/staff", response_model=StaffResponse)
async def create_staff(
    body: StaffCreate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    staff = Staff(business_id=business.id, name=body.name, active=True)
    session.add(staff)
    await session.flush()
    return staff


@router.delete("/api/staff/{staff_id}")
async def delete_staff(
    staff_id: int,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    staff = (await session.execute(
        select(Staff).where(Staff.id == staff_id, Staff.business_id == business.id)
    )).scalar_one_or_none()
    if staff is None:
        raise HTTPException(status_code=404, detail="Staff not found for this business.")
    staff.active = False  # soft-delete keeps historical bookings' staff_id valid
    await session.flush()
    return {"ok": True}
