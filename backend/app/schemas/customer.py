from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    id: int
    business_id: int
    customer_id: int
    content: str
    direction: str
    timestamp: datetime.datetime

    model_config = {"from_attributes": True}


class CustomerResponse(BaseModel):
    id: int
    name: Optional[str] = None
    phone_number: str
    is_regular: bool
    order_count: int
    total_spent: float
    last_order_at: Optional[datetime.datetime] = None
    top_items: list = Field(default_factory=list)
    tags: list = Field(default_factory=list)


class CustomerDetailResponse(CustomerResponse):
    notes: Optional[str] = None
    is_regular_override: Optional[bool] = None
    avg_cadence_days: Optional[float] = None
    recent_orders: list = Field(default_factory=list)


class CustomerUpdate(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=1000)
    tags: Optional[list[str]] = None
    is_regular_override: Optional[bool] = None


class UploadResponse(BaseModel):
    """POST /api/upload response."""
    url: str
