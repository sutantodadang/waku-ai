from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


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


class EmbeddedSignup(BaseModel):
    """POST /api/whatsapp/embedded-signup — finish Meta Embedded Signup.
    Frontend FB.login returns `code`; the WA_EMBEDDED_SIGNUP message event
    returns phone_number_id + waba_id."""
    code: str = Field(..., description="Auth code from FB.login response")
    phone_number_id: str = Field(..., description="From WA_EMBEDDED_SIGNUP event")
    waba_id: str = Field(..., description="WhatsApp Business Account id")


class WhatsAppConnectionResponse(BaseModel):
    is_connected: bool
    phone_number_id: Optional[str] = None
    waba_id: Optional[str] = None
