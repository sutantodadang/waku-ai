# ai/tests/test_match_image.py
"""Tests for match_image_to_catalog in llm.py."""

import llm


CATALOG = [{"name": "Nasi Goreng", "price": 15000}]
FAKE_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def test_match_found(monkeypatch):
    """LLM returns exact product name → matched True."""
    monkeypatch.setattr(llm, "call_openai", lambda *a, **k: "Nasi Goreng")
    result = llm.match_image_to_catalog(FAKE_B64, "image/jpeg", "", CATALOG)
    assert result["matched"] is True
    assert result["product_name"] == "Nasi Goreng"
    assert result["price"] == 15000.0
    assert "Nasi Goreng" in result["reply"]


def test_match_found_case_insensitive(monkeypatch):
    """LLM returns name with different casing → still matched."""
    monkeypatch.setattr(llm, "call_openai", lambda *a, **k: "nasi goreng")
    result = llm.match_image_to_catalog(FAKE_B64, "image/jpeg", "", CATALOG)
    assert result["matched"] is True
    assert result["product_name"] == "Nasi Goreng"


def test_match_not_found_none_response(monkeypatch):
    """LLM returns NONE → matched False."""
    monkeypatch.setattr(llm, "call_openai", lambda *a, **k: "NONE")
    result = llm.match_image_to_catalog(FAKE_B64, "image/jpeg", "", CATALOG)
    assert result["matched"] is False
    assert result["product_name"] == ""
    assert "belum yakin" in result["reply"]


def test_match_not_found_llm_returns_none(monkeypatch):
    """LLM returns None (text-only model fallback) → matched False, ask-to-confirm reply."""
    monkeypatch.setattr(llm, "call_openai", lambda *a, **k: None)
    result = llm.match_image_to_catalog(FAKE_B64, "image/jpeg", "", CATALOG)
    assert result["matched"] is False
    assert result["product_name"] == ""
    assert "belum yakin" in result["reply"]


def test_empty_catalog(monkeypatch):
    """Empty catalog → matched False without calling LLM."""
    called = []
    monkeypatch.setattr(llm, "call_openai", lambda *a, **k: called.append(1) or "Nasi Goreng")
    result = llm.match_image_to_catalog(FAKE_B64, "image/jpeg", "", [])
    assert result["matched"] is False
    assert called == []  # LLM not called


def test_data_uri_prefix_passthrough(monkeypatch):
    """image_b64 already has data: prefix → used as-is."""
    captured = {}

    def fake_call(messages, **kwargs):
        captured["url"] = messages[1]["content"][1]["image_url"]["url"]
        return "Nasi Goreng"

    monkeypatch.setattr(llm, "call_openai", fake_call)
    data_uri = "data:image/png;base64," + FAKE_B64
    llm.match_image_to_catalog(data_uri, "image/jpeg", "goreng", CATALOG)
    assert captured["url"] == data_uri  # unchanged


def test_plain_b64_gets_data_uri(monkeypatch):
    """Plain base64 string → data URI constructed with provided mime_type."""
    captured = {}

    def fake_call(messages, **kwargs):
        captured["url"] = messages[1]["content"][1]["image_url"]["url"]
        return "Nasi Goreng"

    monkeypatch.setattr(llm, "call_openai", fake_call)
    llm.match_image_to_catalog(FAKE_B64, "image/jpeg", "", CATALOG)
    assert captured["url"].startswith("data:image/jpeg;base64,")


def test_reply_price_format(monkeypatch):
    """Price in reply uses Rp with dot thousands separator."""
    catalog = [{"name": "Mie Goreng", "price": 12500}]
    monkeypatch.setattr(llm, "call_openai", lambda *a, **k: "Mie Goreng")
    result = llm.match_image_to_catalog(FAKE_B64, "image/jpeg", "", catalog)
    assert "Rp12.500" in result["reply"]
