"""
Pydantic schemas for request/response serialisation.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Business ────────────────────────────────────────────────────────────────────
class BusinessRegister(BaseModel):
    """POST /api/business/register body."""
    phone_number: str = Field(..., description="Business WhatsApp number (format: 62812...)")
    business_name: str = Field(..., min_length=1, max_length=255)
    settings: Optional[dict] = None


class BusinessResponse(BaseModel):
    id: int
    phone_number: str
    business_name: str
    settings: Optional[dict] = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


# ── Order ───────────────────────────────────────────────────────────────────────
class OrderItem(BaseModel):
    """Single item inside an order."""
    name: str
    quantity: int = 1
    price: Optional[float] = None


class OrderResponse(BaseModel):
    id: int
    business_id: int
    customer_id: int
    items: list[Any]
    total: float
    status: str
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class DailySummary(BaseModel):
    date: str
    total_conversations: int
    total_orders: int
    total_revenue: float
    orders: list[OrderResponse]


# ── Webhook ─────────────────────────────────────────────────────────────────────
class WhatsAppWebhookEntry(BaseModel):
    """Represents a single entry from Meta's webhook payload."""
    id: Optional[str] = None
    changes: list[dict] = []


class WhatsAppWebhookPayload(BaseModel):
    """Top-level incoming webhook body."""
    object: Optional[str] = None
    entry: list[WhatsAppWebhookEntry] = []


# ── Message ─────────────────────────────────────────────────────────────────────
class MessageResponse(BaseModel):
    id: int
    business_id: int
    customer_id: int
    content: str
    direction: str
    timestamp: datetime.datetime

    model_config = {"from_attributes": True}
