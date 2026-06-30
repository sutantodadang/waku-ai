"""Inbound image handling: parse + download + persist + AI match + reply."""
import asyncio
import base64
import os
import tempfile

import pytest
from sqlalchemy import select

from app.core import database
from app import main
from app import models
from app.services import whatsapp as wa
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
    """Captionless image → download → persist inbound (media_url set) → AI match → template reply saved."""

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

    # NO caption — should hit the template/confirm reply path
    img_msg = {
        "from_number": "628999",
        "message_id": "wamid.img99",
        "type": "image",
        "media_id": "MEDIA999",
        "caption": "",
        "text": "",
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
    # Template reply should mention the matched product
    assert "Nasi Goreng" in outbound[0].content, f"reply should mention product: {outbound[0].content}"


def test_inbound_image_with_caption_routes_to_conversational_pipeline(client, monkeypatch):
    """Captioned image → download OK → inbound image saved (media_url set) → caption routed through
    _reply_to_text with save_inbound=False and grounded text containing matched product name."""

    t = register(client, email="cap@x.com", phone="081333333333", business_name="Warung Cap")
    connect_wa(client, t["access_token"], phone_number_id="PNID_CAP", access_token="TKN_CAP")
    biz = _get_business()

    async def fake_download(media_id, *, phone_number_id=None, access_token=None):
        return (b"\x89PNG\r\n\x1a\n", "image/png")

    async def fake_send(*a, **k):
        return {"messages": [{"id": "wamid.cap_out"}]}

    async def fake_match_image(business, image_bytes, mime, caption, catalog):
        return {
            "matched": True,
            "product_name": "Parfum Mawar",
            "price": 50000.0,
            "reply": "Ini Parfum Mawar ya Kak?",
        }

    # Record calls to _reply_to_text
    reply_to_text_calls = []
    _original_reply_to_text = main._reply_to_text

    async def fake_reply_to_text(session, business, customer, text, message_id, *, save_inbound=True):
        reply_to_text_calls.append({
            "text": text,
            "message_id": message_id,
            "save_inbound": save_inbound,
        })
        # Call through so outbound message is saved
        await _original_reply_to_text(session, business, customer, text, message_id, save_inbound=save_inbound)

    monkeypatch.setattr(main, "download_media", fake_download)
    monkeypatch.setattr(main, "send_message", fake_send)
    monkeypatch.setattr(main, "_match_image_with_ai", fake_match_image)
    monkeypatch.setattr(main, "_reply_to_text", fake_reply_to_text)

    img_msg = {
        "from_number": "628777",
        "message_id": "wamid.cap77",
        "type": "image",
        "media_id": "MEDIA777",
        "caption": "apakah ini ada?",
        "text": "apakah ini ada?",
        "timestamp": "1700000077",
    }

    async def _run():
        async with database.async_session_factory() as session:
            await main._process_tenant_messages(session, biz, [img_msg])
            await session.commit()

    asyncio.run(_run())

    # _reply_to_text must have been called exactly once with save_inbound=False
    assert len(reply_to_text_calls) == 1, f"expected 1 _reply_to_text call, got {len(reply_to_text_calls)}"
    call = reply_to_text_calls[0]
    assert call["save_inbound"] is False, "caption path must pass save_inbound=False (inbound image already saved)"
    assert "apakah ini ada?" in call["text"], f"caption must appear in grounded text: {call['text']}"
    assert "Parfum Mawar" in call["text"], f"matched product name must ground the text: {call['text']}"

    # Inbound image row must still be persisted with media_url
    async def _check():
        async with database.async_session_factory() as s:
            msgs = (await s.execute(
                select(models.Message).where(models.Message.business_id == biz.id)
                .order_by(models.Message.id)
            )).scalars().all()
            return msgs

    rows = asyncio.run(_check())
    inbound = [m for m in rows if m.direction == "inbound"]
    assert len(inbound) == 1, f"expected 1 inbound image row, got {len(inbound)}"
    assert inbound[0].media_url is not None, "inbound image must have media_url even when caption is routed"
    assert inbound[0].media_url.startswith("/uploads/")


def test_no_visual_match_with_caption_sends_not_available_not_pipeline(client, monkeypatch):
    """No visual match + caption → outbound 'belum menemukan', _reply_to_text NOT called."""

    t = register(client, email="nomatch@x.com", phone="083333333333", business_name="Warung NM")
    connect_wa(client, t["access_token"], phone_number_id="PNID_NM", access_token="TKN_NM")
    biz = _get_business()

    async def fake_download(media_id, *, phone_number_id=None, access_token=None):
        return (b"\x89PNG\r\n\x1a\n", "image/png")

    async def fake_send(*a, **k):
        return {"messages": [{"id": "wamid.nm_out"}]}

    async def fake_match_image_no_match(business, image_bytes, mime, caption, catalog):
        return {
            "matched": False,
            "product_name": "",
            "price": 0.0,
            "reply": "Maaf Kak, Waku belum menemukan produk yang mirip dengan foto ini di katalog 🙏",
        }

    reply_to_text_calls = []

    async def fake_reply_to_text(session, business, customer, text, message_id, *, save_inbound=True):
        reply_to_text_calls.append(text)

    monkeypatch.setattr(main, "download_media", fake_download)
    monkeypatch.setattr(main, "send_message", fake_send)
    monkeypatch.setattr(main, "_match_image_with_ai", fake_match_image_no_match)
    monkeypatch.setattr(main, "_reply_to_text", fake_reply_to_text)

    img_msg = {
        "from_number": "629111",
        "message_id": "wamid.nm111",
        "type": "image",
        "media_id": "MEDIA_NM",
        "caption": "apakah ada produk ini?",
        "text": "apakah ada produk ini?",
        "timestamp": "1700000111",
    }

    async def _run():
        async with database.async_session_factory() as session:
            await main._process_tenant_messages(session, biz, [img_msg])
            await session.commit()

    asyncio.run(_run())

    # _reply_to_text must NOT have been called (no-match takes priority)
    assert len(reply_to_text_calls) == 0, (
        f"_reply_to_text should NOT be called on no visual match, got calls: {reply_to_text_calls}"
    )

    # Outbound must contain the not-available message
    async def _check():
        async with database.async_session_factory() as s:
            msgs = (await s.execute(
                select(models.Message).where(models.Message.business_id == biz.id)
                .order_by(models.Message.id)
            )).scalars().all()
            return msgs

    rows = asyncio.run(_check())
    outbound = [m for m in rows if m.direction == "outbound"]
    assert len(outbound) == 1, f"expected 1 outbound, got {len(outbound)}"
    assert "belum menemukan" in outbound[0].content, (
        f"outbound must contain 'belum menemukan', got: {outbound[0].content}"
    )


def test_load_product_image_b64_local_file():
    """_load_product_image_b64 returns (b64, mime) for existing local /uploads/ file."""
    # Write a tiny PNG to the real UPLOAD_DIR
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    safe_name = "_test_b64_helper.png"
    dest = os.path.join(main.UPLOAD_DIR, safe_name)
    try:
        with open(dest, "wb") as f:
            f.write(png_bytes)

        result = main._load_product_image_b64(f"/uploads/{safe_name}")
        assert result is not None, "_load_product_image_b64 should return a tuple for existing file"
        b64_str, mime_type = result
        assert mime_type == "image/png"
        assert base64.b64decode(b64_str) == png_bytes
    finally:
        if os.path.exists(dest):
            os.remove(dest)


def test_load_product_image_b64_missing_file():
    """_load_product_image_b64 returns None for a /uploads/ path that does not exist."""
    result = main._load_product_image_b64("/uploads/_nonexistent_file_xyzabc.png")
    assert result is None


def test_load_product_image_b64_none_url():
    """_load_product_image_b64 returns None when image_url is None or empty."""
    assert main._load_product_image_b64(None) is None
    assert main._load_product_image_b64("") is None


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
