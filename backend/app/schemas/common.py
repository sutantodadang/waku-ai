from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class WhatsAppWebhookEntry(BaseModel):
    """Represents a single entry from Meta's webhook payload."""
    id: Optional[str] = None
    changes: list[dict] = []


class WhatsAppWebhookPayload(BaseModel):
    """Top-level incoming webhook body."""
    object: Optional[str] = None
    entry: list[WhatsAppWebhookEntry] = []


class QrisGenerateRequest(BaseModel):
    """POST /api/qris/generate — QRIS payload string to render as PNG."""
    payload: str


class SendPaymentResponse(BaseModel):
    """POST /api/orders/{id}/send-payment response."""
    sent: bool
