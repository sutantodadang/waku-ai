"""Payment delivery — format the business's methods and send within the WA window."""
from __future__ import annotations

import logging

from services.whatsapp import send_image, send_message, within_service_window

logger = logging.getLogger(__name__)


def format_payment_text(business, total: float) -> str:
    lines = [f"Total pesanan: Rp{total:,.0f}".replace(",", ".")]
    methods = business.payment_methods or []
    if methods:
        lines.append("\nSilakan bayar ke salah satu:")
        for m in methods:
            lines.append(f"• {m.get('label', '')}: {m.get('value', '')}")
    lines.append("\nMohon kirim bukti transfer ya Kak 🙏")
    return "\n".join(lines)


async def send_payment_info_text_only(business, total: float, to: str = "") -> bool:
    """Send payment text + QRIS image without a window check (caller already checked)."""
    if not (business.payment_methods or business.qris_image_url):
        return False
    text = format_payment_text(business, total)
    await send_message(
        to, text,
        phone_number_id=business.phone_number_id, access_token=business.access_token,
    )
    if business.qris_image_url:
        try:
            await send_image(
                to, business.qris_image_url,
                phone_number_id=business.phone_number_id, access_token=business.access_token,
            )
        except Exception:
            logger.warning("Failed to send QRIS image")
    return True


async def send_payment_info(session, business, customer, total: float) -> bool:
    """Send payment info to the customer if within the 24h window and methods exist."""
    if not (business.payment_methods or business.qris_image_url):
        logger.info("No payment methods configured for business")
        return False
    if not await within_service_window(session, customer.id):
        logger.info("Outside 24h window — skipping payment send to %s", customer.phone_number)
        return False
    return await send_payment_info_text_only(business, total, to=customer.phone_number)
