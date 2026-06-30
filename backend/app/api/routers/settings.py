from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.constants import DEFAULT_SETTINGS
from app.core.database import get_db
from app.core.security import get_current_business
from app.models import Business
from app.schemas import SettingsResponse, SettingsUpdate

router = APIRouter()


@router.get("/api/settings", response_model=SettingsResponse)
async def dashboard_get_settings(
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """GET /api/settings — return auto-reply settings for the authenticated business.
    Missing keys are filled from DEFAULT_SETTINGS so the dashboard always gets a complete shape."""
    stored = business.settings or {}
    merged = {**DEFAULT_SETTINGS, **stored}
    return SettingsResponse(**merged)


@router.put("/api/settings", response_model=SettingsResponse)
async def dashboard_update_settings(
    body: SettingsUpdate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """PUT /api/settings — merge partial settings into Business.settings JSON."""
    current = dict(business.settings or {})

    update_data = body.model_dump(exclude_unset=True, exclude_none=True)
    if "business_hours" in update_data and isinstance(update_data["business_hours"], dict):
        bh = update_data["business_hours"]
        current_bh = current.get("business_hours", {})
        current["business_hours"] = {**current_bh, **bh}
        update_data.pop("business_hours")
    if "faq" in update_data:
        current["faq"] = [f.model_dump() if hasattr(f, "model_dump") else f for f in body.faq]
        update_data.pop("faq")

    current.update(update_data)
    business.settings = current
    await session.flush()
    return SettingsResponse(**{**DEFAULT_SETTINGS, **current})
