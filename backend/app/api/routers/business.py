from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_business
from app.models import Business
from app.schemas import (
    BusinessProfileUpdate,
    BusinessResponse,
    DailySummary,
    OrderResponse,
)
from app.services.order_service import get_daily_summary, get_orders_for_business

logger = logging.getLogger("waku.backend")

router = APIRouter()


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
    business: Business = Depends(get_current_business),
):
    """List orders for a business, newest first. Scoped to the authenticated owner."""
    if business.id != business_id:
        raise HTTPException(status_code=403, detail="Forbidden.")

    orders = await get_orders_for_business(session, business_id, limit=limit, offset=offset)
    return orders


@router.get("/api/business/{business_id}/summary", response_model=DailySummary)
async def business_summary(
    business_id: int,
    day: Optional[str] = Query(None, description="Date in YYYY-MM-DD format. Defaults to today."),
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """Daily summary of conversations, orders, and revenue. Scoped to the authenticated owner."""
    if business.id != business_id:
        raise HTTPException(status_code=403, detail="Forbidden.")

    target_date = date.fromisoformat(day) if day else date.today()
    summary = await get_daily_summary(session, business_id, day=target_date)
    return summary
