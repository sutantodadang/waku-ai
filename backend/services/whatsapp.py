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
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "waku_verify_123")
APP_SECRET = os.getenv("APP_SECRET", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
API_VERSION = "v18.0"

if PHONE_NUMBER_ID:
    API_BASE = f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}"
else:
    API_BASE = None
    logger.warning("PHONE_NUMBER_ID not set — WhatsApp send API will not work.")


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
async def send_message(to: str, body: str) -> dict:
    """
    Send a plain-text WhatsApp message via Cloud API.
    Returns the API response JSON dict.
    """
    if not API_BASE:
        logger.error("Cannot send message: PHONE_NUMBER_ID is not configured.")
        return {"error": "PHONE_NUMBER_ID not configured"}

    url = f"{API_BASE}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
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


async def send_template_message(to: str, template_name: str, params: Optional[dict] = None) -> dict:
    """
    Send a WhatsApp template (HSM) message.
    `params` should be a dict mapping placeholder names to values.
    """
    if not API_BASE:
        logger.error("Cannot send template: PHONE_NUMBER_ID is not configured.")
        return {"error": "PHONE_NUMBER_ID not configured"}

    url = f"{API_BASE}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
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
