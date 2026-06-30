from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_business
from app.models import Business, Customer, Order
from app.schemas import (
    CustomerDetailResponse,
    CustomerResponse,
    CustomerUpdate,
)
from app.services.order_service import is_regular
from app.api.routers.orders import _order_to_dashboard_dict

router = APIRouter()


def _customer_to_dict(c: Customer) -> dict:
    return {
        "id": c.id,
        "name": None if (c.name or "") == c.phone_number else c.name,
        "phone_number": c.phone_number,
        "is_regular": is_regular(c),
        "order_count": c.order_count or 0,
        "total_spent": c.total_spent or 0.0,
        "last_order_at": c.last_order_at,
        "top_items": c.top_items or [],
        "tags": c.tags or [],
    }


@router.get("/api/customers", response_model=list[CustomerResponse])
async def dashboard_list_customers(
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """GET /api/customers — customers for this business, most recent first."""
    stmt = (
        select(Customer)
        .where(Customer.business_id == business.id)
        .order_by(Customer.last_order_at.desc().nullslast(), Customer.id.desc())
    )
    customers = (await session.execute(stmt)).scalars().all()
    return [_customer_to_dict(c) for c in customers]


@router.get("/api/customers/{customer_id}", response_model=CustomerDetailResponse)
async def dashboard_get_customer(
    customer_id: int,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """GET /api/customers/{id} — profile + recent orders."""
    cust = (await session.execute(
        select(Customer).where(Customer.id == customer_id, Customer.business_id == business.id)
    )).scalar_one_or_none()
    if cust is None:
        raise HTTPException(status_code=404, detail="Customer not found for this business.")

    orders = (await session.execute(
        select(Order).where(Order.customer_id == cust.id).order_by(Order.created_at.desc()).limit(10)
    )).scalars().all()

    data = _customer_to_dict(cust)
    data.update({
        "notes": cust.notes,
        "is_regular_override": cust.is_regular_override,
        "avg_cadence_days": cust.avg_cadence_days,
        "recent_orders": [_order_to_dashboard_dict(o, cust.name or cust.phone_number) for o in orders],
    })
    return data


@router.patch("/api/customers/{customer_id}", response_model=CustomerDetailResponse)
async def dashboard_update_customer(
    customer_id: int,
    body: CustomerUpdate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """PATCH /api/customers/{id} — update owner notes / tags / loyalty override."""
    cust = (await session.execute(
        select(Customer).where(Customer.id == customer_id, Customer.business_id == business.id)
    )).scalar_one_or_none()
    if cust is None:
        raise HTTPException(status_code=404, detail="Customer not found for this business.")

    if body.tags is not None:
        if len(body.tags) > 10 or any(len(t) > 60 for t in body.tags):
            raise HTTPException(status_code=422, detail="Maks 10 tag, tiap tag ≤ 60 karakter.")
        cust.tags = body.tags
    if body.notes is not None:
        cust.notes = body.notes
    if body.is_regular_override is not None:
        cust.is_regular_override = body.is_regular_override
    await session.flush()

    orders = (await session.execute(
        select(Order).where(Order.customer_id == cust.id).order_by(Order.created_at.desc()).limit(10)
    )).scalars().all()
    data = _customer_to_dict(cust)
    data.update({
        "notes": cust.notes,
        "is_regular_override": cust.is_regular_override,
        "avg_cadence_days": cust.avg_cadence_days,
        "recent_orders": [_order_to_dashboard_dict(o, cust.name or cust.phone_number) for o in orders],
    })
    return data
