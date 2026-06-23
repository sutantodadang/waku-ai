"""TDD: ORDER intent parity — 'aku mau' must classify as ORDER, same as 'saya mau'."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import nlu


def test_aku_mau_classifies_as_order():
    assert nlu.classify_intent("aku mau 10 ya") == "ORDER"


def test_saya_mau_still_order_no_regression():
    assert nlu.classify_intent("saya mau 10 ya") == "ORDER"


def test_aku_mw_classifies_as_order():
    # slang: mw → mau via normalize in analyze_message, but classify_intent is called on raw text
    # INTENT_PATTERNS already has r"\baku mw\b" — verify it still works
    assert nlu.classify_intent("aku mw 10 ya") == "ORDER"


def test_aku_mau_pesan_still_order():
    assert nlu.classify_intent("aku mau pesan nasi goreng") == "ORDER"
