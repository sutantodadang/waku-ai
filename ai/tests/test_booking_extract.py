# ai/tests/test_booking_extract.py
import conversation as conv_mod


def test_close_with_date_sets_booking(monkeypatch):
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "ok kak")
    monkeypatch.setattr(conv_mod, "extract_booking_from_chat",
        lambda h, c, bt: {"items": [{"name": "Facial", "price": 80000, "duration_minutes": 60}],
                          "scheduled_at": "2026-07-01T14:00:00", "staff_name": "Sari",
                          "deposit_amount": None, "notes": ""})
    mgr = conv_mod.ConversationManager(); monkeypatch.setattr(conv_mod, "manager", mgr)
    cat = [{"name": "Facial", "price": 80000}]
    conv_mod.generate_reply("628", "booking facial sama sari", catalog=cat, business_type="salon")
    conv_mod.generate_reply("628", "iya itu aja", catalog=cat, business_type="salon")
    conv = mgr.get("628")
    assert conv.closed_booking is not None
    assert conv.closed_booking["status"] == "closed"
    assert conv.closed_booking["scheduled_at"] == "2026-07-01T14:00:00"


def test_ambiguous_date_no_booking(monkeypatch):
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "untuk tanggal berapa ya kak?")
    monkeypatch.setattr(conv_mod, "extract_booking_from_chat",
        lambda h, c, bt: {"items": [{"name": "Facial", "price": 80000}],
                          "scheduled_at": None, "staff_name": None, "deposit_amount": None, "notes": ""})
    mgr = conv_mod.ConversationManager(); monkeypatch.setattr(conv_mod, "manager", mgr)
    cat = [{"name": "Facial", "price": 80000}]
    conv_mod.generate_reply("630", "mau booking facial", catalog=cat, business_type="salon")
    conv_mod.generate_reply("630", "itu aja", catalog=cat, business_type="salon")
    assert mgr.get("630").closed_booking is None  # no date → no booking
