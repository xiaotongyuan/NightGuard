"""Long UI stories and random enabled clicks. FakeLLM only. No browser."""

from __future__ import annotations

import random

import pytest

from nightguard.schema import (
    AIMS,
    BRIGHTNESSES,
    FORBIDDEN_LLM_KEYS,
    LIGHTS,
    MODES,
    POSTURES,
    VERDICTS,
)
from nightguard.ui_session import ALL_CHOICES, FOLLOW_CHOICES, OPEN_CHOICES, UiError, UiSession
from nightguard.llm import WATER_IGNORE

STEP_KINDS = {
    "none",
    "gated",
    "filtered",
    "pass_a",
    "follow",
    "upgrade",
    "pass_b",
    "morning",
    "label",
}
PHASES = {"closed", "watch", "upgraded"}


def assert_snapshot_legal(snap: dict) -> None:
    assert snap["window"]["phase"] in PHASES
    assert snap["last_step"]["kind"] in STEP_KINDS
    assert snap["action"]["light"] in LIGHTS
    assert snap["action"]["mode"] in MODES
    assert snap["action"]["brightness"] in BRIGHTNESSES
    assert snap["action"]["aim"] in AIMS
    assert snap["person"]["posture"] in POSTURES
    enabled = set(snap["enabled_choices"])
    disabled = set(snap["disabled_choices"])
    assert enabled.isdisjoint(disabled)
    assert enabled | disabled == set(ALL_CHOICES)
    if snap["window"]["open"]:
        assert enabled == set(FOLLOW_CHOICES)
    else:
        assert enabled == set(OPEN_CHOICES)
    assert len(snap["memory"]["cards"]) <= 5
    blob = snap.get("llm") or {}
    for side in ("input", "output"):
        data = blob.get(side)
        if isinstance(data, dict):
            assert not any(k in data for k in FORBIDDEN_LLM_KEYS)
    text = " ".join(snap["memory"]["cards"]) + " " + str(snap["memory"].get("habit_text", ""))
    assert "mosquito_draw" not in text
    if snap["memory"]["cards"]:
        assert all("weight" not in line for line in snap["memory"]["cards"])


def _water_night(session: UiSession) -> dict:
    session.play("open.sigh.torso")
    snap = session.play("follow.leave.plus1")
    assert snap["last_step"]["kind"] == "pass_b"
    return snap


def test_WC1_first_night_scratch_then_sit():
    session = UiSession(mode="continue")
    snap = session.play("open.scratch.left_calf")
    assert snap["last_step"]["kind"] == "pass_a"
    assert snap["window"]["phase"] == "watch"
    snap = session.play("follow.sit.plus1")
    assert snap["last_step"]["kind"] == "pass_b"
    assert snap["window"]["phase"] == "closed"
    assert len(session.loop.memory.cards) == 1
    assert session.loop.memory.cards[0]["outcome_15min"] == "sat_up"
    assert_snapshot_legal(snap)


def test_WC5_cold_room_no_card():
    session = UiSession(mode="continue", temp_c=8.0)
    snap = session.play("open.scratch.left_calf")
    assert snap["last_step"]["kind"] == "gated"
    assert snap["last_step"]["llm_called"] is False
    assert session.loop.memory.cards == []
    assert snap["budget"]["pass_a_count"] == 0
    assert_snapshot_legal(snap)


def test_WC7_off_upgrade_sit_card():
    session = UiSession(mode="continue", pass_a_fixture="off")
    session.play("open.scratch.left_calf")
    mid = session.play("follow.scratch.plus6")
    assert mid["last_step"]["kind"] == "upgrade"
    assert mid["action"]["light"] == "on"
    snap = session.play("follow.sit.plus1")
    card = session.loop.memory.cards[0]
    assert card["first_light"] == "off"
    assert card["correction"] == "upgraded_on"
    assert card["light"] == "on"
    assert card["outcome_15min"] == "sat_up"
    assert any("first_light: off" in line and "correction: upgraded_on" in line for line in snap["memory"]["cards"])
    assert_snapshot_legal(snap)


def test_WC8_three_water_nights_update_then_filter():
    session = UiSession(mode="continue")
    _water_night(session)
    session.next_night()
    _water_night(session)
    session.next_night()
    _water_night(session)
    assert len(session.loop.memory.cards) == 3
    assert all(card["first_light"] == "off" for card in session.loop.memory.cards)
    assert all(card["verdict"] == "appropriate" for card in session.loop.memory.cards)
    snap = session.morning()
    assert snap["memory"]["filter_text"] == WATER_IGNORE
    assert snap["night_id"] == "n4"
    assert snap["last_step"]["kind"] == "morning"
    assert WATER_IGNORE in snap["rules"]["soft_diff"]["added"]
    sigh = session.play("open.sigh.torso")
    assert sigh["last_step"]["kind"] == "filtered"
    assert sigh["last_step"]["llm_called"] is False
    assert sigh["budget"]["pass_a_count"] == 0
    scratch = session.play("open.scratch.left_calf")
    assert scratch["last_step"]["kind"] == "pass_a"
    assert scratch["budget"]["pass_a_count"] == 1
    assert_snapshot_legal(scratch)


def test_WC6_three_not_mosquito_scratch_then_habit_on_fourth():
    session = UiSession(mode="continue")
    for _ in range(3):
        session.play("open.scratch.left_calf")
        session.play("follow.wait15")
        session.label("not_mosquito")
        session.next_night()
    snap = session.play("open.scratch.left_calf")
    assert snap["last_step"]["kind"] == "pass_a"
    assert snap["action"]["light"] == "off"
    memory = snap["llm"]["input"]["memory_text"]
    assert "not_mosquito" in memory
    assert "habit: scratch_burst morning not_mosquito" in snap["memory"]["habit_text"]
    assert_snapshot_legal(snap)


@pytest.mark.parametrize("seed", (24, 25, 26))
def test_WX1_random_enabled_clicks_stay_legal(seed: int):
    rng = random.Random(seed)
    session = UiSession(mode="continue", pass_a_fixture="off")
    snap = session.snapshot()
    assert_snapshot_legal(snap)
    for _ in range(80):
        if not snap["window"]["open"] and rng.random() < 0.12:
            if rng.random() < 0.4:
                snap = session.morning()
            elif rng.random() < 0.5:
                snap = session.next_night()
            else:
                snap = session.label(rng.choice(("mosquito", "not_mosquito", "unsure")))
            assert_snapshot_legal(snap)
            continue
        choice = rng.choice(snap["enabled_choices"])
        snap = session.play(choice)
        assert_snapshot_legal(snap)
    disabled = snap["disabled_choices"]
    if disabled:
        with pytest.raises(UiError) as exc:
            session.play(disabled[0])
        assert exc.value.code == "choice_disabled"
    for card in session.loop.memory.cards:
        assert card["verdict"] in VERDICTS
        assert card.get("x") is None
