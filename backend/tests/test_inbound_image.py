"""Inbound image handling: parse + download + persist + AI match + reply."""
import asyncio

import pytest
from sqlalchemy import select

import database
import main
import models
import services.whatsapp as wa
from helpers import register, connect_wa


# ── unit: parse_whatsapp_message handles image type ──────────────────────────

def test_parse_image_message():
    payload = {"entry": [{"changes": [{"value": {
        "messaging_product": "whatsapp",
        "metadata": {"phone_number_id": "PNID"},
        "messages": [{
            "from": "628111",
            "id": "wamid.img1",
            "type": "image",
            "image": {"id": "MEDIA123", "caption": "ini nasi goreng"},
            "timestamp": "1700000000",
        }],
    }}]}]}

    msgs = wa.parse_whatsapp_message(payload)
    assert len(msgs) == 1
    m = msgs[0]
    assert m["type"] == "image"
    assert m["media_id"] == "MEDIA123"
    assert m["caption"] == "ini nasi goreng"
    assert m["text"] == "ini nasi goreng"   # caption echoed as text
    assert m["from_number"] == "628111"
    assert m["message_id"] == "wamid.img1"
    assert m["timestamp"] == "1700000000"


def test_parse_text_message_unchanged():
    """Legacy text messages still carry all original keys + new keys with defaults."""
    payload = {"entry": [{"changes": [{"value": {
        "messaging_product": "whatsapp",
        "metadata": {"phone_number_id": "PNID"},
        "messages": [{
            "from": "628222",
            "id": "wamid.txt1",
            "type": "text",
            "text": {"body": "halo"},
            "timestamp": "1700000001",
        }],
    }}]}]}

    msgs = wa.parse_whatsapp_message(payload)
    assert len(msgs) == 1
    m = msgs[0]
    assert m["type"] == "text"
    assert m["text"] == "halo"
    assert m["media_id"] is None
    assert m["caption"] == ""
    assert m["from_number"] == "628222"


# ── integration: _process_tenant_messages with image ─────────────────────────

def _get_business():
    async def _get():
        async with database.async_session_factory() as s:
            return (await s.execute(select(models.Business))).scalars().first()
    return asyncio.run(_get())


def test_inbound_image_saves_messages_and_replies(client, monkeypatch):
    """Full path: image msg → download → persist inbound (media_url set) → AI match → outbound saved."""

    # Register + connect
    t = register(client)
    connect_wa(client, t["access_token"], phone_number_id="PNID_IMG", access_token="TKN_IMG")
    biz = _get_business()

    # Monkeypatches
    async def fake_download(media_id, *, phone_number_id=None, access_token=None):
        return (b"\x89PNG\r\n\x1a\n", "image/png")

    async def fake_send(*a, **k):
        return {"messages": [{"id": "wamid.out"}]}

    async def fake_match_image(business, image_bytes, mime, caption, catalog):
        return {
            "matched": True,
            "product_name": "Nasi Goreng",
            "price": 15000.0,
            "reply": "Ini Nasi Goreng ya Kak?",
        }

    monkeypatch.setattr(main, "download_media", fake_download)
    monkeypatch.setattr(main, "send_message", fake_send)
    monkeypatch.setattr(main, "_match_image_with_ai", fake_match_image)

    img_msg = {
        "from_number": "628999",
        "message_id": "wamid.img99",
        "type": "image",
        "media_id": "MEDIA999",
        "caption": "ini foto makanan",
        "text": "ini foto makanan",
        "timestamp": "1700000099",
    }

    async def _run():
        async with database.async_session_factory() as session:
            await main._process_tenant_messages(session, biz, [img_msg])
            await session.commit()

    asyncio.run(_run())

    # Verify DB state
    async def _check():
        async with database.async_session_factory() as s:
            msgs = (await s.execute(
                select(models.Message).where(models.Message.business_id == biz.id)
                .order_by(models.Message.id)
            )).scalars().all()
            return msgs

    rows = asyncio.run(_check())

    inbound = [m for m in rows if m.direction == "inbound"]
    outbound = [m for m in rows if m.direction == "outbound"]

    assert len(inbound) == 1, f"expected 1 inbound, got {len(inbound)}"
    assert inbound[0].media_url is not None, "inbound message must have media_url set"
    assert inbound[0].media_url.startswith("/uploads/")

    assert len(outbound) == 1, f"expected 1 outbound, got {len(outbound)}"
    assert "Nasi Goreng" in outbound[0].content, f"reply should mention product: {outbound[0].content}"


def test_inbound_image_graceful_on_download_failure(client, monkeypatch):
    """When download_media returns None, a graceful Indonesian reply is saved."""

    t = register(client, email="b@x.com", phone="082222222222", business_name="Warung B")
    connect_wa(client, t["access_token"], phone_number_id="PNID_IMG2", access_token="TKN_IMG2")
    biz = _get_business()

    async def fake_download_fail(media_id, *, phone_number_id=None, access_token=None):
        return None

    async def fake_send(*a, **k):
        return {"messages": [{"id": "wamid.out2"}]}

    monkeypatch.setattr(main, "download_media", fake_download_fail)
    monkeypatch.setattr(main, "send_message", fake_send)

    img_msg = {
        "from_number": "628888",
        "message_id": "wamid.img88",
        "type": "image",
        "media_id": "MEDIA888",
        "caption": "",
        "text": "",
        "timestamp": "1700000088",
    }

    async def _run():
        async with database.async_session_factory() as session:
            await main._process_tenant_messages(session, biz, [img_msg])
            await session.commit()

    asyncio.run(_run())

    async def _check():
        async with database.async_session_factory() as s:
            msgs = (await s.execute(
                select(models.Message).where(models.Message.business_id == biz.id)
                .order_by(models.Message.id)
            )).scalars().all()
            return msgs

    rows = asyncio.run(_check())

    inbound = [m for m in rows if m.direction == "inbound"]
    outbound = [m for m in rows if m.direction == "outbound"]

    assert len(inbound) == 1
    assert inbound[0].media_url is None  # no file saved when download failed
    assert len(outbound) == 1
    assert "gambar" in outbound[0].content.lower() or "Waku" in outbound[0].content
