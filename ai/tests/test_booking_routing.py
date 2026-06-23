import conversation as conv_mod
from nlu import classify_intent


def test_booking_intent_detected():
    assert classify_intent("mau booking facial besok jam 2") == "BOOKING"


def test_warung_does_not_enter_booking_flow(monkeypatch):
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "halo kak")
    called = {"booking": False}
    monkeypatch.setattr(conv_mod, "_handle_booking_flow",
                        lambda *a, **k: called.__setitem__("booking", True) or None)
    mgr = conv_mod.ConversationManager(); monkeypatch.setattr(conv_mod, "manager", mgr)
    conv_mod.generate_reply("628", "mau booking", catalog=[{"name": "Facial", "price": 80000}], business_type="warung")
    assert called["booking"] is False


def test_salon_enters_booking_flow(monkeypatch):
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "halo kak")
    called = {"booking": False}
    monkeypatch.setattr(conv_mod, "_handle_booking_flow",
                        lambda *a, **k: called.__setitem__("booking", True) or "ok")
    mgr = conv_mod.ConversationManager(); monkeypatch.setattr(conv_mod, "manager", mgr)
    conv_mod.generate_reply("629", "mau booking", catalog=[{"name": "Facial", "price": 80000}], business_type="salon")
    assert called["booking"] is True
