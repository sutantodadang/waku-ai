from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel, Field


class StaffCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class StaffResponse(BaseModel):
    id: int
    name: str
    active: bool

    model_config = {"from_attributes": True}


class BookingResponse(BaseModel):
    id: int
    customer_name: str
    staff_id: Optional[int] = None
    items: list = Field(default_factory=list)
    total: float
    deposit_amount: Optional[float] = None
    scheduled_at: Optional[datetime.datetime] = None
    duration_minutes: Optional[int] = None
    status: str
    notes: Optional[str] = None
    clash: bool = False
    created_at: datetime.datetime


class BookingUpdate(BaseModel):
    status: Optional[str] = Field(default=None, pattern="^(requested|confirmed|rejected|completed|cancelled)$")
    scheduled_at: Optional[datetime.datetime] = None
    staff_id: Optional[int] = None
