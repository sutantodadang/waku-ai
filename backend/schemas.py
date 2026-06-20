"""
Pydantic schemas for request/response serialisation.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field


# ── Auth ────────────────────────────────────────────────────────────────────────
class UserRegister(BaseModel):
    """POST /api/auth/register — sign up an owner and create their business."""
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    business_name: str = Field(..., min_length=1, max_length=255)
    phone_number: str = Field(..., description="Display WhatsApp number, e.g. 0812...")


class UserLogin(BaseModel):
    """POST /api/auth/login — email + password."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    business_id: Optional[int] = None
    business_name: Optional[str] = None


# ── Reverse-OTP (WhatsApp) ──────────────────────────────────────────────────────
class OTPRequest(BaseModel):
    """POST /api/auth/otp/request — issue a code the owner will send from WhatsApp."""
    phone_number: str = Field(..., description="Owner's WhatsApp number")
    purpose: str = Field("login", pattern="^(login|connect)$")


class OTPRequestResponse(BaseModel):
    code: str
    expires_at: datetime.datetime
    instructions: str
    platform_number: Optional[str] = None  # number the owner sends the code TO


class OTPVerify(BaseModel):
    """POST /api/auth/otp/verify — confirm the owner sent the code from WhatsApp.
    The code (from /otp/request) is required so only the requester can verify."""
    phone_number: str
    code: str = Field(..., min_length=4, max_length=32)


# ── Connect WhatsApp (manual / pre-Embedded-Signup) ─────────────────────────────
class ConnectWhatsApp(BaseModel):
    """PUT /api/whatsapp/connect — attach Meta WhatsApp credentials to the business.
    Used for manual/test wiring; Embedded Signup fills the same fields automatically."""
    phone_number_id: str = Field(..., description="Meta phone_number_id (webhook routing id)")
    waba_id: Optional[str] = None
    access_token: str = Field(..., description="Meta send token (stored encrypted)")


class WhatsAppConnectionResponse(BaseModel):
    is_connected: bool
    phone_number_id: Optional[str] = None
    waba_id: Optional[str] = None


# ── Business ────────────────────────────────────────────────────────────────────
class BusinessRegister(BaseModel):
    """POST /api/business/register body."""
    phone_number: str = Field(..., description="Business WhatsApp number (format: 62812...)")
    business_name: str = Field(..., min_length=1, max_length=255)
    settings: Optional[dict] = None


class BusinessProfileUpdate(BaseModel):
    """PATCH /api/business — rename the authenticated business."""
    business_name: str = Field(..., min_length=1, max_length=255)


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


# ── Product ─────────────────────────────────────────────────────────────────────
class ProductCreate(BaseModel):
    """POST /api/products body."""
    name: str = Field(..., min_length=1, max_length=255)
    price: float = Field(..., ge=0)
    description: Optional[str] = None
    image_url: Optional[str] = None


class ProductUpdate(BaseModel):
    """PUT /api/products/{id} body — all fields optional."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    price: Optional[float] = Field(None, ge=0)
    description: Optional[str] = None
    image_url: Optional[str] = None


class ProductResponse(BaseModel):
    id: int
    business_id: int
    name: str
    price: float
    description: Optional[str] = None
    image_url: Optional[str] = None
    created_at: datetime.datetime

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


# ── Order status update + dashboard order shape ────────────────────────────────
class OrderStatusUpdate(BaseModel):
    """PATCH /api/orders/{id} body — dashboard sends Indonesian status."""
    status: str  # baru | diproses | selesai | dibatalkan


class OrderDashboardResponse(BaseModel):
    """Order shape expected by the Streamlit dashboard."""
    id: int
    customer_name: str
    status: str  # Indonesian label
    total: float
    items: list[Any]
    created_at: datetime.datetime


class DashboardSummary(BaseModel):
    """GET /api/dashboard/summary shape expected by the dashboard."""
    orders_today: int
    revenue_today: float
    messages_handled: int
    pending_orders: int
    top_products: list[dict]


class UploadResponse(BaseModel):
    """POST /api/upload response."""
    url: str
