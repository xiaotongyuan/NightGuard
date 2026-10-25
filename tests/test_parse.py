import json

import pytest

from nightguard.events import make_event
from nightguard.llm import (
    FakeLLM,
    fallback_pass_a,
    invoke,
    parse_pass_a_json,
    parse_pass_b_json,
    sanitize_pass_a,
)
from tests.cases import sample_pass_b_no_new_event


def _valid(**over):
    body = {
        "reasoning": "Still lying. Scratch burst. Low belief.",
        "belief_state": "possible_harassment",
        "belief_p": 0.34,
        "mode": "silent_confirm",
    }
    body.update(over)
    return json.dumps(body)


def test_P1_flat_legal_json_passes():
    event = make_event()
    parsed = parse_pass_a_json(_valid())
    out = sanitize_pass_a(event, parsed)
    assert out["light"] == "on"
    assert out["belief_state"] == "possible_harassment"


def test_P2_nested_retries_then_fallback():
    nested = json.dumps({"action": {"light": "off"}, "reasoning": "bad"})
    event = make_event()
    client = FakeLLM(script=[nested, nested])
    out, attempts, failed = invoke(client, "pass_a", {}, event)
    assert attempts == 2
    assert failed is True
    assert out["light"] == "off"
    assert out["reasoning"] == fallback_pass_a(event)["reasoning"]
    assert out["aim"] == "none"


def test_P3_aim_overwritten_from_body_zone():
    event = make_event(body_zone="left_calf")
    parsed = parse_pass_a_json(_valid())
    out = sanitize_pass_a(event, parsed)
    assert out["aim"] == "floor_left"


def test_P4_mode_none_derives_light_off_fields():
    event = make_event()
    parsed = parse_pass_a_json(_valid(mode="none"))
    out = sanitize_pass_a(event, parsed)
    assert out["mode"] == "none"
    assert out["brightness"] == "none"
    assert out["duration_s"] == 0
    assert out["aim"] == "none"


def test_P5_lie_stable_forces_awake_false():
    event = make_event(posture="lie_stable")
    raw = _valid()
    parsed = parse_pass_a_json(raw)
    assert set(parsed) == {"reasoning", "belief_state", "belief_p", "mode"}
    out = sanitize_pass_a(event, parsed)
    assert out["awake"] is False
    client = FakeLLM(script=[raw])
    invoked, _, failed = invoke(client, "pass_a", {}, event)
    assert failed is False
    assert invoked["awake"] is False
    assert invoked is not parsed


def test_P6_no_new_event_forces_inconclusive_even_if_model_says_appropriate():
    raw = json.dumps(
        {
            "verdict": "appropriate",
            "revised_belief_p": 0.4,
            "reason": "outcome_15min=no_new_event; later_motion_type=none.",
        }
    )
    out, _, failed = invoke(
        FakeLLM(script=[raw]),
        "pass_b",
        sample_pass_b_no_new_event(),
        {},
    )
    assert failed is False
    assert out["verdict"] == "inconclusive"


def test_P7_assist_search_derives_action_fields():
    event = make_event(body_zone="right_foot", posture="sit")
    out = sanitize_pass_a(event, parse_pass_a_json(_valid(mode="assist_search")))
    assert out["awake"] is True
    assert (out["light"], out["brightness"], out["duration_s"], out["aim"]) == (
        "on", "medium", 6, "floor_right"
    )


def test_P8_probabilities_must_be_finite_and_between_zero_and_one():
    for value in (-0.1, 1.1, float("nan")):
        with pytest.raises(ValueError):
            parse_pass_a_json(_valid(belief_p=value))
        with pytest.raises(ValueError):
            parse_pass_b_json(
                json.dumps(
                    {
                        "verdict": "appropriate",
                        "revised_belief_p": value,
                        "reason": "outcome_15min=settled_lie; later_motion_type=none.",
                    }
                )
            )
