"""
WhatsApp Cloud API integration — send messages & verify webhooks.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────────────────────
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "waku_verify_123")
APP_SECRET = os.getenv("APP_SECRET", "")
API_VERSION = "v21.0"

# Platform-level credentials — the OWN number Waku uses for the reverse-OTP /
# system channel. Per-business sends pass their own phone_number_id + token.
# Accept several env names for backward compat (.env.example used WHATSAPP_PHONE_NUMBER_ID).
PLATFORM_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PLATFORM_PHONE_NUMBER_ID = (
    os.getenv("PLATFORM_PHONE_NUMBER_ID")
    or os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    or os.getenv("PHONE_NUMBER_ID")
    or ""
)

GRAPH_BASE = f"https://graph.facebook.com/{API_VERSION}"


def _resolve_credentials(phone_number_id: Optional[str], access_token: Optional[str]) -> tuple[str, str]:
    """Pick per-business creds when given, else fall back to platform creds."""
    return (phone_number_id or PLATFORM_PHONE_NUMBER_ID, access_token or PLATFORM_TOKEN)


def extract_phone_number_id(payload: dict) -> Optional[str]:
    """Pull `metadata.phone_number_id` from a Meta webhook payload (routing key)."""
    try:
        return (
            payload.get("entry", [{}])[0]
            .get("changes", [{}])[0]
            .get("value", {})
            .get("metadata", {})
            .get("phone_number_id")
        )
    except (IndexError, AttributeError):
        return None


# ── Webhook verification ────────────────────────────────────────────────────────
def verify_webhook(mode: str, token: str, challenge: str) -> Optional[str]:
    """
    Handle Meta's webhook verification handshake.
    Returns the challenge string if tokens match, else None.
    """
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully.")
        return challenge
    logger.warning("Webhook verification failed — token mismatch.")
    return None


def verify_signature(payload_body: bytes, x_hub_signature_256: Optional[str]) -> bool:
    """
    Verify that the incoming webhook payload was signed by Meta.
    Uses APP_SECRET to compute HMAC‑SHA256 and compare.
    """
    if not APP_SECRET or not x_hub_signature_256:
        logger.debug("Signature verification skipped (APP_SECRET or header missing).")
        return True  # skip verification when not configured

    expected = "sha256=" + hmac.new(
        APP_SECRET.encode(), payload_body, hashlib.sha256
    ).hexdigest()

    if hmac.compare_digest(expected, x_hub_signature_256):
        logger.debug("Webhook signature verified.")
        return True

    logger.error("Webhook signature MISMATCH — possible spoofed request.")
    return False


# ── Send messages ───────────────────────────────────────────────────────────────
async def send_message(
    to: str,
    body: str,
    *,
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """
    Send a plain-text WhatsApp message via Cloud API.
    Pass a business's `phone_number_id` + `access_token` to send from that
    business's number; omit both to use the platform number.
    Returns the API response JSON dict.
    """
    pid, token = _resolve_credentials(phone_number_id, access_token)
    if not pid or not token:
        logger.error("Cannot send message: no phone_number_id/token (business not connected).")
        return {"error": "whatsapp_not_configured"}

    url = f"{GRAPH_BASE}/{pid}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info("Message sent to %s — wamid=%s", to, data.get("messages", [{}])[0].get("id"))
            return data
        except httpx.HTTPStatusError as exc:
            logger.error("WhatsApp API error [%s]: %s", exc.response.status_code, exc.response.text)
            raise
        except httpx.RequestError as exc:
            logger.error("WhatsApp API request failed: %s", exc)
            raise


async def send_template_message(
    to: str,
    template_name: str,
    params: Optional[dict] = None,
    *,
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """
    Send a WhatsApp template (HSM) message.
    `params` should be a dict mapping placeholder names to values.
    """
    pid, token = _resolve_credentials(phone_number_id, access_token)
    if not pid or not token:
        logger.error("Cannot send template: no phone_number_id/token configured.")
        return {"error": "whatsapp_not_configured"}

    url = f"{GRAPH_BASE}/{pid}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    components: list[dict] = []
    if params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": v} for v in params.values()],
        })

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "id"},  # Indonesian
            "components": components,
        },
    }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info("Template '%s' sent to %s", template_name, to)
            return data
        except httpx.HTTPStatusError as exc:
            logger.error("WhatsApp template API error [%s]: %s", exc.response.status_code, exc.response.text)
            raise
        except httpx.RequestError as exc:
            logger.error("WhatsApp template request failed: %s", exc)
            raise


# ── Utility ─────────────────────────────────────────────────────────────────────
def parse_statuses(payload: dict) -> list[dict]:
    """
    Extract delivery-status callbacks (sent / delivered / read / failed) from a
    Meta webhook payload, including any error code+detail on failure.
    """
    out: list[dict] = []
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                for st in change.get("value", {}).get("statuses", []):
                    out.append({
                        "status": st.get("status"),
                        "recipient_id": st.get("recipient_id"),
                        "errors": [
                            {
                                "code": e.get("code"),
                                "title": e.get("title"),
                                "detail": (e.get("error_data") or {}).get("details"),
                            }
                            for e in st.get("errors", [])
                        ],
                    })
    except Exception as exc:
        logger.error("Failed to parse statuses: %s", exc)
    return out


def parse_whatsapp_message(payload: dict) -> list[dict]:
    """
    Extract inbound messages from a Meta webhook payload.
    Returns a list of dicts with keys: from_number, message_id, text, timestamp.
    """
    messages: list[dict] = []
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if value.get("messaging_product") != "whatsapp":
                    continue
                for msg in value.get("messages", []):
                    messages.append({
                        "from_number": msg.get("from"),
                        "message_id": msg.get("id"),
                        "text": msg.get("text", {}).get("body", ""),
                        "timestamp": msg.get("timestamp"),
                    })
    except Exception as exc:
        logger.error("Failed to parse webhook payload: %s", exc)
    return messages
