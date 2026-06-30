from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    """POST /api/products body."""
    name: str = Field(..., min_length=1, max_length=255)
    price: float = Field(..., ge=0)
    description: Optional[str] = None
    image_url: Optional[str] = None
    duration_minutes: Optional[int] = Field(default=None, ge=0)


class ProductUpdate(BaseModel):
    """PUT /api/products/{id} body — all fields optional."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    price: Optional[float] = Field(None, ge=0)
    description: Optional[str] = None
    image_url: Optional[str] = None
    duration_minutes: Optional[int] = Field(default=None, ge=0)


class ProductResponse(BaseModel):
    id: int
    business_id: int
    name: str
    price: float
    description: Optional[str] = None
    image_url: Optional[str] = None
    duration_minutes: Optional[int] = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}
