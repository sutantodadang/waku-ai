"""
TDD: LLM provider routing — verifies ask_llm honours settings.llm_provider.

Run from ai/ directory:
    python -m pytest tests/test_llm_provider_routing.py -v
"""

import pytest
import llm


# ---------------------------------------------------------------------------
# Helper: a sentinel so we can tell "was this function called?"
# ---------------------------------------------------------------------------

class _CallTracker:
    def __init__(self, return_value):
        self.calls = []
        self._return_value = return_value

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self._return_value

    @property
    def called(self):
        return bool(self.calls)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MESSAGES = [{"role": "user", "content": "halo"}]


# ---------------------------------------------------------------------------
# Case 1: provider="openai", OpenAI returns content → use it, NEVER Ollama
# ---------------------------------------------------------------------------

def test_openai_provider_returns_content_no_ollama(monkeypatch):
    ollama_tracker = _CallTracker("should-not-be-used")

    monkeypatch.setattr(llm.settings, "llm_provider", "openai")
    monkeypatch.setattr(llm, "call_openai", _CallTracker("hai kak"))
    monkeypatch.setattr(llm, "call_ollama", ollama_tracker)

    result = llm.ask_llm(MESSAGES, intent="GREETING")

    assert result == "hai kak"
    assert not ollama_tracker.called, "call_ollama must NOT be called when provider=openai"


# ---------------------------------------------------------------------------
# Case 2: provider="openai", OpenAI returns None → rule fallback, NEVER Ollama
# ---------------------------------------------------------------------------

def test_openai_provider_empty_content_falls_back_to_rules_not_ollama(monkeypatch):
    ollama_tracker = _CallTracker("ollama-should-not-run")

    monkeypatch.setattr(llm.settings, "llm_provider", "openai")
    monkeypatch.setattr(llm, "call_openai", _CallTracker(None))
    monkeypatch.setattr(llm, "call_ollama", ollama_tracker)

    result = llm.ask_llm(MESSAGES, intent="GREETING")

    # Must return a non-empty rule-based response, NOT an Ollama response
    assert result  # not empty
    assert result != "ollama-should-not-run"
    assert not ollama_tracker.called, "call_ollama must NOT be called when provider=openai"


# ---------------------------------------------------------------------------
# Case 3: provider="auto", OpenAI None → try Ollama and return its content
# ---------------------------------------------------------------------------

def test_auto_provider_falls_back_to_ollama_when_openai_empty(monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_provider", "auto")
    # use_openai depends on llm_provider + openai_api_key; set key so use_openai=True
    monkeypatch.setattr(llm.settings, "openai_api_key", "fake-key")
    monkeypatch.setattr(llm, "call_openai", _CallTracker(None))
    ollama_tracker = _CallTracker("dari ollama")
    monkeypatch.setattr(llm, "call_ollama", ollama_tracker)

    result = llm.ask_llm(MESSAGES, intent="UNKNOWN")

    assert result == "dari ollama"
    assert ollama_tracker.called, "call_ollama MUST be called in auto mode when OpenAI fails"


# ---------------------------------------------------------------------------
# Case 4: provider="ollama", Ollama returns content → use it, NEVER OpenAI
# ---------------------------------------------------------------------------

def test_ollama_provider_never_calls_openai(monkeypatch):
    openai_tracker = _CallTracker("should-not-be-used")

    monkeypatch.setattr(llm.settings, "llm_provider", "ollama")
    monkeypatch.setattr(llm, "call_openai", openai_tracker)
    monkeypatch.setattr(llm, "call_ollama", _CallTracker("ollama only"))

    result = llm.ask_llm(MESSAGES, intent="ORDER")

    assert result == "ollama only"
    assert not openai_tracker.called, "call_openai must NOT be called when provider=ollama"


# ---------------------------------------------------------------------------
# _extract_content pure-helper tests (no httpx mocking needed)
# ---------------------------------------------------------------------------

def _make_response(content=None, reasoning_content=None):
    """Build a minimal OpenAI-compatible response dict."""
    msg = {}
    if content is not None:
        msg["content"] = content
    if reasoning_content is not None:
        msg["reasoning_content"] = reasoning_content
    return {"choices": [{"message": msg}]}


def test_extract_content_returns_content_when_present():
    data = _make_response(content="  halo kak  ", reasoning_content="ignored")
    assert llm._extract_content(data) == "halo kak"


def test_extract_content_uses_reasoning_when_content_empty():
    # Real nemotron-nano payload: content="" but reasoning_content has the answer
    data = _make_response(
        content="",
        reasoning_content="Halo! Parfum ada, bisa beli Rp10.000. Ada stoknya.",
    )
    result = llm._extract_content(data)
    assert result == "Halo! Parfum ada, bisa beli Rp10.000. Ada stoknya."


def test_extract_content_strips_think_blocks_from_reasoning():
    data = _make_response(
        content="",
        reasoning_content="<think>internal chain of thought</think>answer",
    )
    assert llm._extract_content(data) == "answer"


def test_extract_content_returns_none_when_both_empty():
    data = _make_response(content="", reasoning_content="   ")
    assert llm._extract_content(data) is None


def test_extract_content_returns_none_on_malformed_dict():
    assert llm._extract_content({}) is None
    assert llm._extract_content({"choices": []}) is None
    assert llm._extract_content(None) is None
