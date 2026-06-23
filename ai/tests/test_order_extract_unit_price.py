"""TDD: extract_order_from_chat must yield UNIT prices (not line totals).

The backend multiplies price * qty, so `price` in each item MUST be the
per-unit price.  The LLM sometimes returns the line total in `price`
(e.g. 10 × Nasi Goreng: price=140000, qty=10, total=140000).
`_normalize_unit_prices` in conversation.py detects and corrects this.
"""
import json
import pytest
import conversation as conv_mod


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_chat():
    return [{"role": "user", "content": "pesan 10 nasi goreng"}]


def _llm_json(items, total=None, notes=""):
    payload = {"items": items, "notes": notes}
    if total is not None:
        payload["total"] = total
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_line_total_price_normalized_to_unit(monkeypatch):
    """LLM returns line total in price field → should be corrected to unit price."""
    # 10 × Nasi Goreng @14000 each → line total 140000
    # LLM incorrectly puts 140000 as price
    raw = _llm_json(
        items=[{"name": "Nasi Goreng", "qty": 10, "price": 140000}],
        total=140000,
    )
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **kw: raw)

    result = conv_mod.extract_order_from_chat(_make_chat(), catalog=None)

    assert result["total"] == 140000, "total preserved"
    assert len(result["items"]) == 1
    assert result["items"][0]["price"] == 14000, "price normalized to unit price"


def test_already_unit_price_unchanged(monkeypatch):
    """LLM returns correct unit price → must NOT be altered."""
    raw = _llm_json(
        items=[{"name": "Nasi Goreng", "qty": 10, "price": 14000}],
        total=140000,
    )
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **kw: raw)

    result = conv_mod.extract_order_from_chat(_make_chat(), catalog=None)

    assert result["total"] == 140000
    assert result["items"][0]["price"] == 14000, "unit price must stay 14000"


def test_two_item_line_total_normalized(monkeypatch):
    """Multi-item: both line totals normalized, overall total preserved."""
    # 2 × Nasi Goreng @14000 = 28000, 3 × Es Teh @5000 = 15000, total 43000
    # LLM emits line totals: 28000 and 15000
    raw = _llm_json(
        items=[
            {"name": "Nasi Goreng", "qty": 2, "price": 28000},
            {"name": "Es Teh", "qty": 3, "price": 15000},
        ],
        total=43000,
    )
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **kw: raw)

    result = conv_mod.extract_order_from_chat(_make_chat(), catalog=None)

    assert result["total"] == 43000
    prices = {it["name"]: it["price"] for it in result["items"]}
    assert prices["Nasi Goreng"] == 14000, "Nasi Goreng unit price"
    assert prices["Es Teh"] == 5000, "Es Teh unit price"


def test_zero_total_no_crash(monkeypatch):
    """LLM returns total=0 with a single qty=1 item → no crash, price unchanged."""
    raw = _llm_json(
        items=[{"name": "Nasi Goreng", "qty": 1, "price": 14000}],
        total=0,
    )
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **kw: raw)

    result = conv_mod.extract_order_from_chat(_make_chat(), catalog=None)

    # total=0 → guard bails out, price must not be touched
    assert result["items"][0]["price"] == 14000
    # total recalculated from unit_sum since LLM gave 0
    # (the existing "if total==0 and items" block fires BEFORE _normalize,
    #  so total becomes 14000 after recalculation; guard then sees unit_sum==total → no change)
    assert result["total"] == 14000
