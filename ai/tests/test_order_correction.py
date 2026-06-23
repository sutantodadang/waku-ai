"""Tests for the hybrid order-correction and close-rebuild logic.

Covers:
  1. CORRECTION: customer says "harusnya 2 bukan 1" → conv.order rebuilt from LLM extractor.
  2. CLOSE: on close the summary and closed_order both come from the rebuilt extraction.
  3. Empty-extraction guard: if LLM returns empty items, conv.order is left untouched.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import conversation as conv_mod

CATALOG = [{"name": "Parfum", "price": 10000}]


def _make_mgr(monkeypatch):
    mgr = conv_mod.ConversationManager()
    monkeypatch.setattr(conv_mod, "manager", mgr)
    return mgr


# ──────────────────────────────────────────────────────────────────────────────
# 1. CORRECTION path
# ──────────────────────────────────────────────────────────────────────────────

def test_correction_rebuilds_order(monkeypatch):
    """'pesanan ini harusnya 2 bukan 1' → reply says perbaiki + x2, order qty=2, still active."""
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "LLM_FALLBACK")
    monkeypatch.setattr(
        conv_mod,
        "extract_order_from_chat",
        lambda history, catalog: {
            "items": [{"name": "Parfum", "qty": 2, "price": 10000}],
            "total": 20000,
            "notes": "",
        },
    )
    mgr = _make_mgr(monkeypatch)

    # Seed active order with qty=1
    conv = mgr.get_or_create("c1")
    conv.set_catalog(CATALOG)
    conv.order.active = True
    conv.order.add_item("Parfum", 1, 10000)
    assert conv.order.items[0]["qty"] == 1

    reply = conv_mod.generate_reply(
        "c1", "pesanan ini harusnya 2 bukan 1", catalog=CATALOG
    )

    assert "perbaiki" in reply.lower(), f"Expected 'perbaiki' in reply: {reply!r}"
    assert "x2" in reply, f"Expected x2 in reply: {reply!r}"
    assert conv.order.items[0]["qty"] == 2, f"qty should be 2, got {conv.order.items[0]['qty']}"
    assert conv.order.active is True, "Order must stay active after correction"


# ──────────────────────────────────────────────────────────────────────────────
# 2. CLOSE: summary and dashboard agree
# ──────────────────────────────────────────────────────────────────────────────

def test_close_summary_matches_dashboard(monkeypatch):
    """On close, reply summary and closed_order total+qty both come from the rebuild."""
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "LLM_FALLBACK")
    monkeypatch.setattr(
        conv_mod,
        "extract_order_from_chat",
        lambda history, catalog: {
            "items": [{"name": "Parfum", "qty": 2, "price": 10000}],
            "total": 20000,
            "notes": "",
        },
    )
    mgr = _make_mgr(monkeypatch)

    # Seed active order with any qty (could be stale)
    conv = mgr.get_or_create("c2")
    conv.set_catalog(CATALOG)
    conv.order.active = True
    conv.order.add_item("Parfum", 1, 10000)  # stale qty=1

    reply = conv_mod.generate_reply("c2", "iya itu aja", catalog=CATALOG)

    assert "Siap Kak" in reply, f"Expected 'Siap Kak' in reply: {reply!r}"
    assert "x2" in reply, f"Expected x2 in close reply: {reply!r}"

    closed = conv.closed_order
    assert closed is not None, "closed_order must be set"
    assert closed["total"] == 20000, f"closed_order total should be 20000, got {closed['total']}"
    assert closed["items"][0]["qty"] == 2, f"closed_order item qty should be 2, got {closed['items'][0]['qty']}"

    # Summary total in reply must match closed_order total (both 20000 → "20,000")
    assert "20,000" in reply or "20000" in reply, f"Reply total must reflect rebuild: {reply!r}"


# ──────────────────────────────────────────────────────────────────────────────
# 3. Empty-extraction guard
# ──────────────────────────────────────────────────────────────────────────────

def test_empty_extraction_leaves_order_intact(monkeypatch):
    """If LLM returns empty items on correction, conv.order.items is NOT wiped."""
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "LLM_FALLBACK")
    monkeypatch.setattr(
        conv_mod,
        "extract_order_from_chat",
        lambda history, catalog: {"items": [], "total": 0},
    )
    mgr = _make_mgr(monkeypatch)

    conv = mgr.get_or_create("c3")
    conv.set_catalog(CATALOG)
    conv.order.active = True
    conv.order.add_item("Parfum", 2, 10000)

    # Trigger correction path
    conv_mod.generate_reply(
        "c3", "pesanan ini harusnya 3 bukan 2", catalog=CATALOG
    )

    # Items untouched — still 1 item, qty=2
    assert len(conv.order.items) == 1, "Item list must be unchanged on empty extraction"
    assert conv.order.items[0]["qty"] == 2, f"qty must stay 2, got {conv.order.items[0]['qty']}"
