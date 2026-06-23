"""TDD: ask-then-order — customer asks about a product, then orders by qty only.

Scenario:
  Turn 1: "halo, apakah parfumnya ada?"  → INQUIRY_STOCK, sets last_product="Parfum"
  Turn 2: "oke aku mau 10 ya"            → ORDER, no product in message, carry last_product
  Expected: order active, reply contains "Parfum", "x10", and price total.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import conversation as conv_mod


CATALOG = [{"name": "Parfum", "price": 10000}]


def test_ask_then_order_carries_last_product(monkeypatch):
    """Turn 1 inquiry → Turn 2 order without restating product → order captured."""
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "LLM_FALLBACK")
    mgr = conv_mod.ConversationManager()
    monkeypatch.setattr(conv_mod, "manager", mgr)

    # Turn 1: stock inquiry — sets last_product
    r1 = conv_mod.generate_reply("s1", "halo, apakah parfumnya ada?", catalog=CATALOG)
    # Turn 2: order without product name — should carry last_product
    r2 = conv_mod.generate_reply("s1", "oke aku mau 10 ya", catalog=CATALOG)

    assert r2 != "LLM_FALLBACK", f"Fell through to LLM; got: {r2!r}"
    assert "Parfum" in r2, f"Product name missing in reply: {r2!r}"
    assert "x10" in r2, f"Quantity missing in reply: {r2!r}"
    # price = 10000 * 10 = 100000 → OrderState.summary uses Python's {:,.0f} → "100,000"
    assert "100,000" in r2 or "100.000" in r2 or "100000" in r2, f"Total missing in reply: {r2!r}"

    conv = mgr.get("s1")
    assert conv.order.active is True, "Order should be active after carry"


def test_no_context_guard_no_order_fabricated(monkeypatch):
    """Fresh session: 'aku mau 10 ya' with no prior product turn must NOT start an order."""
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "LLM_FALLBACK")
    mgr = conv_mod.ConversationManager()
    monkeypatch.setattr(conv_mod, "manager", mgr)

    r1 = conv_mod.generate_reply("s2", "aku mau 10 ya", catalog=CATALOG)

    conv = mgr.get("s2")
    # No last_product set → must NOT have started an order via carry
    assert conv.order.active is False, f"Order should not be fabricated; active={conv.order.active}, reply={r1!r}"
    # Should show menu fallback (contains "Parfum" listing or "menu")
    assert "Parfum" in r1 or "menu" in r1.lower(), f"Expected menu fallback, got: {r1!r}"


def test_quantity_detached_from_product_name(monkeypatch):
    """'boleh parfumnya, aku mau pesen 2 ya' → qty 2 even though '2' isn't adjacent to the name."""
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "LLM_FALLBACK")
    mgr = conv_mod.ConversationManager()
    monkeypatch.setattr(conv_mod, "manager", mgr)

    r = conv_mod.generate_reply("s4", "boleh parfumnya, aku mau pesen 2 ya", catalog=CATALOG)

    assert r != "LLM_FALLBACK", f"Fell through to LLM; got: {r!r}"
    assert "Parfum" in r, f"Product name missing: {r!r}"
    assert "x2" in r, f"Quantity should be 2: {r!r}"
    conv = mgr.get("s4")
    assert conv.order.active is True


def test_nlu_single_product_detached_number(monkeypatch):
    """Unit: analyze_message pairs a lone detached number with a single product."""
    from nlu import analyze_message
    a = analyze_message("boleh parfumnya, aku mau pesen 2 ya", catalog_items=["Parfum"])
    assert a["entities"]["product_names"] == ["Parfum"]
    assert a["entities"]["product_quantities"] == [2]


def test_last_product_field_set_after_stock_inquiry(monkeypatch):
    """last_product is populated after a product is mentioned in inquiry."""
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "LLM_FALLBACK")
    mgr = conv_mod.ConversationManager()
    monkeypatch.setattr(conv_mod, "manager", mgr)

    conv_mod.generate_reply("s3", "apakah parfumnya ada?", catalog=CATALOG)
    conv = mgr.get("s3")
    assert conv.last_product is not None, "last_product should be set after product mention"
    assert conv.last_product.lower() == "parfum"
