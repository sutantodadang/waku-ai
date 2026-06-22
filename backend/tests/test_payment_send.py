"""Payment text formats methods; image sent only when URL set; skipped when no methods."""
import asyncio
import datetime

import services.payment as pay
import services.whatsapp as wa


class _Biz:
    def __init__(self, methods, qris=None):
        self.business_name = "Warung"
        self.payment_methods = methods
        self.qris_image_url = qris
        self.phone_number_id = "PNID"
        self.access_token = "TKN"


def test_format_payment_text_lists_methods():
    biz = _Biz([{"type": "rekening", "label": "BCA", "value": "123 a.n. Tini"}])
    text = pay.format_payment_text(biz, 28000)
    assert "28.000" in text or "28000" in text
    assert "BCA" in text and "123 a.n. Tini" in text


def test_send_payment_skips_when_no_methods(monkeypatch):
    sent = []
    monkeypatch.setattr(pay, "send_message", lambda *a, **k: sent.append(("text", a)))
    biz = _Biz([])

    async def _run():
        return await pay.send_payment_info_text_only(biz, 1000)

    out = asyncio.run(_run())
    assert out is False and sent == []
