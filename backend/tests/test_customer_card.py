"""The customer card must never fabricate for unknown customers."""
import datetime as dt
import types
from app.api.routers import webhook


def _c(**kw):
    base = dict(id=1, phone_number="628111", name="628111", business_id=1,
                notes=None, tags=[], is_regular_override=None, order_count=0,
                total_spent=0.0, last_order_at=None, top_items=[], avg_cadence_days=None)
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_new_unknown_customer_gets_no_card():
    assert webhook._build_customer_card(_c()) is None


def test_known_regular_customer_card():
    c = _c(name="Budi", order_count=8, top_items=[{"name": "Nasi Goreng", "count": 9}],
           last_order_at=dt.datetime(2026, 6, 1), avg_cadence_days=5.0, tags=["tanpa pedas"])
    card = webhook._build_customer_card(c)
    assert card["name"] == "Budi"
    assert card["is_regular"] is True
    assert card["usual_items"] == ["Nasi Goreng"]
    assert card["tags"] == ["tanpa pedas"]


def test_card_present_for_named_customer_without_orders():
    # A customer the owner named/annotated but who hasn't ordered yet still gets a card.
    c = _c(name="Budi", notes="langganan lama")
    card = webhook._build_customer_card(c)
    assert card is not None and card["name"] == "Budi"
