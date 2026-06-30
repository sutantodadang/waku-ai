from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_business
from app.models import Business
from app.schemas import (
    BusinessProfileUpdate,
    BusinessRegister,
    BusinessResponse,
    DailySummary,
    OrderResponse,
)
from app.services.order_service import get_daily_summary, get_orders_for_business

logger = logging.getLogger("waku.backend")

router = APIRouter()


@router.post("/api/business/register", response_model=BusinessResponse)
async def register_business(body: BusinessRegister, session: AsyncSession = Depends(get_db)):
    """
    Register a new business (UMKM) in the system.
    """
    # Check existing
    stmt = select(Business).where(Business.phone_number == body.phone_number)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Business with this phone number already registered.")

    business = Business(
        phone_number=body.phone_number,
        business_name=body.business_name,
        settings=body.settings or {},
    )
    session.add(business)
    await session.flush()
    logger.info("Business #%d '%s' registered.", business.id, business.business_name)
    return business


@router.get("/api/business", response_model=BusinessResponse)
async def get_business_profile(
    business: Business = Depends(get_current_business),
):
    """GET /api/business — the authenticated owner's business profile."""
    return business


@router.patch("/api/business", response_model=BusinessResponse)
async def update_business_profile(
    body: BusinessProfileUpdate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """PATCH /api/business — rename the authenticated owner's business."""
    business.business_name = body.business_name
    if body.payment_methods is not None:
        business.payment_methods = [m.model_dump() for m in body.payment_methods]
    if body.qris_image_url is not None:
        business.qris_image_url = body.qris_image_url or None
    if body.business_type is not None:
        business.business_type = body.business_type
    await session.flush()
    return business


@router.get("/api/business/{business_id}/orders", response_model=list[OrderResponse])
async def list_orders(
    business_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """List orders for a business, newest first."""
    # Verify business exists
    stmt = select(Business).where(Business.id == business_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Business not found.")

    orders = await get_orders_for_business(session, business_id, limit=limit, offset=offset)
    return orders


@router.get("/api/business/{business_id}/summary", response_model=DailySummary)
async def business_summary(
    business_id: int,
    day: Optional[str] = Query(None, description="Date in YYYY-MM-DD format. Defaults to today."),
    session: AsyncSession = Depends(get_db),
):
    """Daily summary of conversations, orders, and revenue."""
    # Verify business
    stmt = select(Business).where(Business.id == business_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Business not found.")

    target_date = date.fromisoformat(day) if day else date.today()
    summary = await get_daily_summary(session, business_id, day=target_date)
    return summary
