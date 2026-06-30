from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class BusinessRegister(BaseModel):
    """POST /api/business/register body."""
    phone_number: str = Field(..., description="Business WhatsApp number (format: 62812...)")
    business_name: str = Field(..., min_length=1, max_length=255)
    settings: Optional[dict] = None


class PaymentMethod(BaseModel):
    type: str = Field(..., pattern="^(qris|rekening|ewallet)$")
    label: str = Field(..., min_length=1, max_length=60)
    value: str = Field(..., min_length=1, max_length=120)


class BusinessProfileUpdate(BaseModel):
    """PATCH /api/business — rename + payment config (all optional except name)."""
    business_name: str = Field(..., min_length=1, max_length=255)
    payment_methods: Optional[list[PaymentMethod]] = Field(default=None, max_length=10)
    qris_image_url: Optional[str] = Field(default=None, max_length=512)
    business_type: Optional[str] = Field(default=None, pattern="^(warung|salon|wedding)$")


class BusinessResponse(BaseModel):
    id: int
    phone_number: str
    business_name: str
    settings: Optional[dict] = None
    created_at: datetime.datetime
    payment_methods: list = Field(default_factory=list)
    qris_image_url: Optional[str] = None
    business_type: str = "warung"

    @field_validator("payment_methods", mode="before")
    @classmethod
    def _none_to_list(cls, v):
        return v or []

    model_config = {"from_attributes": True}


# ── Settings (auto-reply) ───────────────────────────────────────────────────────
class FAQItem(BaseModel):
    question: str = ""
    answer: str = ""


class BusinessHours(BaseModel):
    open: str = "08:00"
    close: str = "21:00"


class SettingsUpdate(BaseModel):
    """PUT /api/settings body — all fields optional."""
    auto_reply_enabled: Optional[bool] = None
    greeting_message: Optional[str] = None
    after_hours_message: Optional[str] = None
    business_hours: Optional[BusinessHours] = None
    faq: Optional[list[FAQItem]] = None


class SettingsResponse(BaseModel):
    auto_reply_enabled: bool = True
    greeting_message: str = ""
    after_hours_message: str = ""
    business_hours: BusinessHours = Field(default_factory=BusinessHours)
    faq: list[FAQItem] = Field(default_factory=list)
