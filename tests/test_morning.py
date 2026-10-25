"""Morning brief, local FakeLLM only. Same payloads as remote."""

import json

from nightguard.events import make_event
from nightguard.llm import FakeLLM, fallback_morning, invoke, parse_morning_json
from nightguard.loop import NightLoop
from tests.cases import sample_morning_input
from tests.helpers import add_minutes, off_pass_a_json, seed_card


def test_MB1_flat_morning_json_parses():
    raw = json.dumps(
        {
            "brief": "Night n2: one dim confirm.",
            "timeline": "03:12 scratch_burst -> sat_up",
            "filter_text": "none",
        }
    )
    parsed = parse_morning_json(raw)
    assert parsed["filter_text"] == "none"


def test_MB2_nested_morning_falls_back_to_yesterday():
    nested = json.dumps({"filter": {"text": "ignore motion scratch_burst"}})
    payload = sample_morning_input()
    payload["yesterday_filter"] = "ignore ~01:55-02:15 motion sigh_shift"
    client = FakeLLM(script=[nested, nested])
    out, attempts, failed = invoke(client, "morning", payload, {})
    assert attempts == 2
    assert failed is True
    assert out == fallback_morning(payload)
    assert out["filter_text"] == payload["yesterday_filter"]


def test_MB3_window_open_refuses_brief():
    loop = NightLoop()
    loop.on_event(make_event(t="02:00:00", motion_type="scratch_burst"))
    assert loop.window.is_open is True
    assert loop.run_morning_brief() is None
    assert loop.morning_refused == "window_open"
    assert loop.morning_llm_calls == 0
    assert loop.llm_calls_tonight == 1


def test_MB4_brief_does_not_spend_night_budget():
    loop = NightLoop()
    start = "02:00:00"
    loop.on_event(make_event(t=start, motion_type="scratch_burst"))
    loop.advance_clock(add_minutes(start, 15))
    night_before = loop.llm_calls_tonight
    out = loop.run_morning_brief()
    assert out is not None
    assert loop.llm_calls_tonight == night_before
    assert loop.morning_llm_calls == 1


def test_MB5_once_per_night():
    loop = NightLoop()
    start = "02:00:00"
    loop.on_event(make_event(t=start, motion_type="scratch_burst"))
    loop.advance_clock(add_minutes(start, 15))
    first = loop.run_morning_brief()
    second = loop.run_morning_brief()
    assert first == second
    assert loop.morning_refused == "already_done"
    assert loop.morning_llm_calls == 1


def test_MB6_accepted_filter_is_applied():
    line = "ignore ~01:55-02:15 motion sigh_shift"
    raw = json.dumps(
        {
            "brief": "Water habit. Ignore that band.",
            "timeline": "02:00 sigh_shift -> left_bed",
            "filter_text": line,
        }
    )
    loop = NightLoop(llm=FakeLLM(script=[raw]))
    loop.memory.cards.extend(
        [
            seed_card(night_id="n1", t="01:55:00", motion_type="sigh_shift"),
            seed_card(night_id="n2", t="02:00:00", motion_type="sigh_shift"),
            seed_card(night_id="n3", t="02:15:00", motion_type="sigh_shift"),
        ]
    )
    loop.current_night = "n4"
    out = loop.run_morning_brief()
    assert out["filter_text"] == line
    before = loop.pass_a_count
    loop.on_event(make_event(night_id="n4", t="02:10:00", motion_type="sigh_shift", body_zone="torso"))
    assert loop.pass_a_count == before


def test_MB7_flush_then_brief_when_clock_hits_0700():
    loop = NightLoop(llm=FakeLLM(script=[off_pass_a_json()]))
    loop.on_event(make_event(t="06:45:00", motion_type="scratch_burst"))
    assert loop.window.is_open is True
    out = loop.run_morning_brief(now_t="07:00:00")
    assert out is not None
    assert loop.window.is_open is False
    assert loop.morning_refused is None
