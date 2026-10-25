"""Gemini remote twins. Default pytest skips these. At most three HTTP calls."""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from nightguard.events import make_event
from nightguard.adapter import RemoteLLM
from nightguard.llm import has_forbidden_keys, invoke
from tests.cases import sample_morning_input, sample_pass_a_input, sample_pass_b_no_new_event

pytestmark = pytest.mark.remote


def _client() -> RemoteLLM:
    load_dotenv()
    if os.getenv("NIGHTGUARD_REMOTE") != "1":
        pytest.skip("set NIGHTGUARD_REMOTE=1 to spend Gemini quota")
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        pytest.skip("GEMINI_API_KEY missing")
    return RemoteLLM(provider="gemini", api_key=key)


@pytest.fixture(scope="module")
def remote_llm():
    return _client()


@pytest.fixture(scope="module")
def remote_bundle(remote_llm):
    event = make_event(t="03:12:40", motion_type="scratch_burst", body_zone="left_calf")
    pass_a, a_attempts, a_fail = invoke(remote_llm, "pass_a", sample_pass_a_input(), event)
    pass_b, b_attempts, b_fail = invoke(remote_llm, "pass_b", sample_pass_b_no_new_event(), event)
    morning, m_attempts, m_fail = invoke(remote_llm, "morning", sample_morning_input(), {})
    return {
        "pass_a": pass_a,
        "pass_b": pass_b,
        "morning": morning,
        "attempts": a_attempts + b_attempts + m_attempts,
        "failed": (a_fail, b_fail, m_fail),
    }


def test_R1_gemini_pass_a_is_flat_legal(remote_bundle):
    out = remote_bundle["pass_a"]
    assert remote_bundle["failed"][0] is False
    assert out["light"] in ("off", "on")
    assert out["mode"] in ("none", "silent_confirm", "assist_search")
    assert out["aim"] in ("none", "floor_left", "floor_right", "wall_head", "wall_side", "wall_right")


def test_R2_gemini_no_new_event_is_inconclusive(remote_bundle):
    out = remote_bundle["pass_b"]
    assert remote_bundle["failed"][1] is False
    assert out["verdict"] == "inconclusive"


def test_R3_gemini_has_no_forbidden_keys(remote_bundle):
    assert has_forbidden_keys(remote_bundle["pass_a"]) is False
    assert has_forbidden_keys(remote_bundle["pass_b"]) is False
    assert has_forbidden_keys(remote_bundle["morning"]) is False
    blob = str(remote_bundle)
    assert "peak_hz" not in blob
    assert "n_mosquitoes" not in blob


def test_RM1_gemini_morning_has_filter_text(remote_bundle):
    out = remote_bundle["morning"]
    assert remote_bundle["failed"][2] is False
    assert isinstance(out["brief"], str)
    assert isinstance(out["filter_text"], str)
    assert remote_bundle["attempts"] <= 6
