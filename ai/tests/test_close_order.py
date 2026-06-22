import conversation as conv_mod


def test_close_sets_closed_order(monkeypatch):
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "Baik kak")
    monkeypatch.setattr(
        conv_mod, "extract_order_from_chat",
        lambda history, catalog: {"items": [{"name": "Nasi Goreng", "qty": 2, "price": 14000}], "total": 28000, "notes": ""},
    )
    mgr = conv_mod.ConversationManager()
    monkeypatch.setattr(conv_mod, "manager", mgr)
    catalog = [{"name": "Nasi Goreng", "price": 14000}]
    conv_mod.generate_reply("628", "pesan 2 nasi goreng", catalog=catalog)
    conv_mod.generate_reply("628", "itu aja", catalog=catalog)
    conv = mgr.get("628")
    assert conv.closed_order is not None
    assert conv.closed_order["status"] == "closed"
    assert conv.closed_order["items"][0]["name"] == "Nasi Goreng"


def test_non_close_turn_has_no_closed_order(monkeypatch):
    monkeypatch.setattr(conv_mod, "ask_llm", lambda *a, **k: "Baik kak")
    mgr = conv_mod.ConversationManager()
    monkeypatch.setattr(conv_mod, "manager", mgr)
    conv_mod.generate_reply("629", "halo kak", catalog=[{"name": "Nasi Goreng", "price": 14000}])
    assert mgr.get("629").closed_order is None
