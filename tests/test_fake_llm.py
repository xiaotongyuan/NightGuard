"""FakeLLM demo replies. No network."""

import json

from nightguard.llm import (
    SCRATCH_IGNORE,
    WATER_IGNORE,
    FakeLLM,
    suggested_morning_filter,
)


def test_FL1_morning_writes_water_ignore_when_habit_and_yesterday_none():
    payload = {
        "yesterday_filter": "none",
        "habit_text": "habit: ~02:00 outcome_15min=left_bed x3 | motion_counts: sigh_shift x3 (±30min)",
        "morning_label": "none",
    }
    assert suggested_morning_filter(payload) == WATER_IGNORE
    raw = FakeLLM().complete("morning", payload)
    assert json.loads(raw)["filter_text"] == WATER_IGNORE


def test_FL2_morning_copies_yesterday():
    payload = {
        "yesterday_filter": WATER_IGNORE,
        "habit_text": "habit: ~02:00 outcome_15min=left_bed x3 | motion_counts: sigh_shift x3 (±30min)",
        "morning_label": "none",
    }
    assert suggested_morning_filter(payload) == WATER_IGNORE
    raw = FakeLLM().complete("morning", payload)
    assert json.loads(raw)["filter_text"] == WATER_IGNORE


def test_FL3_morning_writes_bare_ignore_for_not_mosquito_habit():
    payload = {
        "yesterday_filter": "none",
        "habit_text": "habit: scratch_burst morning not_mosquito x3",
        "morning_label": "not_mosquito",
    }
    assert suggested_morning_filter(payload) == SCRATCH_IGNORE


def test_FL4_empty_habit_stays_none():
    payload = {"yesterday_filter": "none", "habit_text": "none", "morning_label": "none"}
    assert suggested_morning_filter(payload) == "none"
    raw = FakeLLM().complete("morning", payload)
    assert json.loads(raw)["filter_text"] == "none"


def test_FL5_sigh_observes_without_light_but_scratch_uses_dim_light():
    base = {"memory_text": "none", "active_filter": "none"}
    sigh = json.loads(FakeLLM().complete("pass_a", {**base, "motion_type": "sigh_shift"}))
    scratch = json.loads(FakeLLM().complete("pass_a", {**base, "motion_type": "scratch_burst"}))
    assert sigh["mode"] == "none"
    assert scratch["mode"] == "silent_confirm"


def test_FL6_not_mosquito_memory_keeps_same_motion_dark():
    payload = {
        "motion_type": "scratch_burst",
        "memory_text": "habit: scratch_burst morning not_mosquito x3",
        "active_filter": "none",
    }
    out = json.loads(FakeLLM().complete("pass_a", payload))
    assert out["belief_state"] == "quiet"
    assert out["belief_p"] <= 0.3
    assert out["mode"] == "none"
