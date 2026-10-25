"""Local twins of R1–R3. Same payloads as remote. No network."""

from nightguard.events import make_event
from nightguard.llm import FakeLLM, has_forbidden_keys, invoke, parse_pass_a_json, parse_pass_b_json
from tests.cases import sample_pass_a_input, sample_pass_b_no_new_event


def test_RL1_fake_pass_a_parses_same_payload_as_remote():
    event = make_event()
    out, attempts, failed = invoke(FakeLLM(), "pass_a", sample_pass_a_input(), event)
    assert failed is False
    assert attempts == 1
    assert set(out) >= {"reasoning", "light", "mode", "aim"}
    assert has_forbidden_keys(out) is False


def test_RL2_fake_no_new_event_is_inconclusive():
    payload = sample_pass_b_no_new_event()
    out, _, failed = invoke(FakeLLM(), "pass_b", payload, {})
    assert failed is False
    assert payload["outcome_15min"] == "no_new_event"
    assert out["verdict"] == "inconclusive"
    assert "outcome_15min" in out["reason"]


def test_RL3_fake_outputs_have_no_forbidden_keys():
    event = make_event()
    a, _, _ = invoke(FakeLLM(), "pass_a", sample_pass_a_input(), event)
    b, _, _ = invoke(FakeLLM(), "pass_b", sample_pass_b_no_new_event(), event)
    raw_a = parse_pass_a_json(FakeLLM().complete("pass_a", sample_pass_a_input()))
    raw_b = parse_pass_b_json(FakeLLM().complete("pass_b", sample_pass_b_no_new_event()))
    assert has_forbidden_keys(a) is False
    assert has_forbidden_keys(b) is False
    assert has_forbidden_keys(raw_a) is False
    assert has_forbidden_keys(raw_b) is False
