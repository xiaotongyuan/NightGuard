"""Guided example walk. FakeLLM. No browser."""

from __future__ import annotations

import json

from nightguard.example_walk import (
    FINISHED_MESSAGE,
    LEFT_MESSAGE,
    RESTART_BUTTON,
    SCRIPT,
    START_BUTTON,
    ExampleWalk,
)
from nightguard.llm import WATER_IGNORE, FakeLLM
from nightguard.ui_session import UiSession

from tests.test_ui_flows import assert_snapshot_legal


class _DownweightMorning(FakeLLM):
    def complete(self, kind: str, payload: dict) -> str:
        if kind == "morning":
            self.calls.append((kind, payload))
            return json.dumps(
                {
                    "brief": "Clock habit is mixed.",
                    "timeline": "none",
                    "filter_text": "downweight ~01:55-02:15 motion sigh_shift",
                }
            )
        return super().complete(kind, payload)


def _walk_to_morning(session: UiSession) -> None:
    for _ in range(3):
        session.play("open.sigh.torso")
        session.play("follow.leave.plus1")
        if session.night_id != "n3":
            session.next_night()


def _highlight(snap: dict) -> dict:
    return snap["example"]["highlight"]


def test_E0_fresh_session_is_idle():
    walk = ExampleWalk()
    view = walk.view()
    assert view["state"] == "idle"
    assert view["message"] == ""
    assert view["button"] == START_BUTTON
    assert view["highlight"]["list_index"] == -1
    snap = UiSession(mode="continue").snapshot()
    assert snap["example"]["state"] == "idle"
    assert_snapshot_legal(snap)


def test_E1_start_highlights_first_sigh():
    snap = UiSession(mode="continue", start_example=True).snapshot()
    assert snap["example"]["state"] == "guiding"
    assert snap["example"]["step"] == 0
    assert snap["example"]["message"] == "Next: sigh shift"
    assert snap["example"]["button"] == RESTART_BUTTON
    assert _highlight(snap)["choice_id"] == "open.sigh.torso"
    assert _highlight(snap)["list_index"] == 0
    assert_snapshot_legal(snap)


def test_E2_happy_path_cues_then_finishes():
    session = UiSession(mode="continue", start_example=True)
    expected = [
        ("play", "open.sigh.torso", "Next: leave bed (+1 min)", "follow.leave.plus1"),
        ("play", "follow.leave.plus1", "Next: Time → next night", ""),
        ("next_night", None, "Next: sigh shift", "open.sigh.torso"),
        ("play", "open.sigh.torso", "Next: leave bed (+1 min)", "follow.leave.plus1"),
        ("play", "follow.leave.plus1", "Next: Time → next night", ""),
        ("next_night", None, "Next: sigh shift", "open.sigh.torso"),
        ("play", "open.sigh.torso", "Next: leave bed (+1 min)", "follow.leave.plus1"),
        ("play", "follow.leave.plus1", "Next: Update tomorrow's rules", ""),
        ("morning", None, "Next: sigh shift", "open.sigh.torso"),
        ("play", "open.sigh.torso", "Next: scratch left calf", "open.scratch.left_calf"),
    ]
    snap = session.snapshot()
    for kind, choice, message, next_choice in expected:
        assert snap["example"]["state"] == "guiding"
        if kind == "play":
            snap = session.play(choice)
        elif kind == "next_night":
            snap = session.next_night()
        else:
            snap = session.morning()
        assert snap["example"]["message"] == message
        assert _highlight(snap)["choice_id"] == next_choice
        assert_snapshot_legal(snap)
    assert snap["last_step"]["kind"] == "filtered"
    assert snap["window"]["open"] is False
    assert "open.scratch.left_calf" in snap["enabled_choices"]
    snap = session.play("open.scratch.left_calf")
    assert snap["example"]["state"] == "finished"
    assert snap["example"]["message"] == FINISHED_MESSAGE
    assert snap["example"]["button"] == RESTART_BUTTON
    assert _highlight(snap)["list_index"] == -1
    assert _highlight(snap)["choice_id"] == ""
    assert snap["last_step"]["kind"] == "pass_a"
    assert snap["memory"]["filter_text"] == WATER_IGNORE
    assert_snapshot_legal(snap)


def test_E3_finished_stays_finished_after_more_clicks():
    session = UiSession(mode="continue", start_example=True)
    for _ in range(3):
        session.play("open.sigh.torso")
        session.play("follow.leave.plus1")
        if session.night_id != "n3":
            session.next_night()
    session.morning()
    session.play("open.sigh.torso")
    session.play("open.scratch.left_calf")
    snap = session.play("follow.leave.plus1")
    assert snap["example"]["state"] == "finished"
    assert snap["example"]["message"] == FINISHED_MESSAGE
    assert snap["last_step"]["kind"] == "pass_b"
    assert_snapshot_legal(snap)


def test_E4_scratch_first_leaves_and_room_still_plays():
    session = UiSession(mode="continue", start_example=True)
    snap = session.play("open.scratch.left_calf")
    assert snap["example"]["state"] == "left"
    assert snap["example"]["message"] == LEFT_MESSAGE
    assert snap["example"]["button"] == RESTART_BUTTON
    assert _highlight(snap)["list_index"] == -1
    assert snap["last_step"]["kind"] == "pass_a"
    snap = session.play("follow.leave.plus1")
    assert snap["example"]["state"] == "left"
    assert snap["last_step"]["kind"] == "pass_b"
    assert_snapshot_legal(snap)


def test_E5_restart_clears_room_and_guides_again():
    left = UiSession(mode="continue", start_example=True)
    left.play("open.scratch.left_calf")
    assert left.snapshot()["example"]["state"] == "left"
    fresh = UiSession(mode="continue", start_example=True)
    snap = fresh.snapshot()
    assert snap["example"]["state"] == "guiding"
    assert snap["night_id"] == "n1"
    assert snap["memory"]["cards"] == []
    assert snap["memory"]["filter_text"] == "none"
    assert snap["example"]["message"] == "Next: sigh shift"
    leftover = FakeLLM()
    leftover.last_remote = {
        "url": "https://api.tokenfactory.nebius.com/v1/chat/completions",
        "model": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    }
    leftover.last_fallback = None
    restart = UiSession(mode="continue", start_example=True, llm=leftover)
    cleared = restart.snapshot()
    assert cleared["night_id"] == "n1"
    assert cleared["llm"]["input"] is None
    assert cleared["llm"]["remote"] is None
    assert_snapshot_legal(snap)
    assert_snapshot_legal(cleared)


def test_E6_label_and_temp_do_not_leave():
    session = UiSession(mode="continue", start_example=True)
    session.label("mosquito")
    session.set_ui({"temp_c": 26.4})
    snap = session.snapshot()
    assert snap["example"]["state"] == "guiding"
    assert snap["example"]["step"] == 0
    snap = session.play("open.sigh.torso")
    assert snap["example"]["state"] == "guiding"
    assert snap["example"]["step"] == 1
    assert_snapshot_legal(snap)


def test_E7_reset_or_early_next_or_early_morning_leaves():
    reset = UiSession(mode="continue", start_example=True)
    snap = reset.reset_night()
    assert snap["example"]["state"] == "left"

    jumped = UiSession(mode="continue", start_example=True)
    snap = jumped.next_night()
    assert snap["example"]["state"] == "left"
    assert snap["night_id"] == "n2"

    early = UiSession(mode="continue", start_example=True)
    snap = early.morning()
    assert snap["example"]["state"] == "left"
    assert snap["last_step"]["kind"] == "morning"
    assert_snapshot_legal(snap)


def test_E8_wrong_follow_or_extra_same_night_leaves():
    waited = UiSession(mode="continue", start_example=True)
    waited.play("open.sigh.torso")
    snap = waited.play("follow.wait15")
    assert snap["example"]["state"] == "left"
    assert snap["last_step"]["kind"] == "pass_b"

    extra = UiSession(mode="continue", start_example=True)
    extra.play("open.sigh.torso")
    extra.play("follow.leave.plus1")
    snap = extra.play("open.sigh.torso")
    assert snap["example"]["state"] == "left"
    assert snap["night_id"] == "n1"
    assert_snapshot_legal(snap)


def test_E9_next_night_instead_of_morning_leaves():
    session = UiSession(mode="continue", start_example=True)
    for _ in range(3):
        session.play("open.sigh.torso")
        session.play("follow.leave.plus1")
        if session.night_id != "n3":
            session.next_night()
    snap = session.next_night()
    assert snap["example"]["state"] == "left"
    assert snap["night_id"] == "n4"
    assert snap["memory"]["filter_text"] == "none"
    assert_snapshot_legal(snap)


def test_E13_example_morning_pins_ignore_so_night4_scratch_stays_open():
    session = UiSession(mode="continue", start_example=True, llm=_DownweightMorning())
    _walk_to_morning(session)
    snap = session.morning()
    assert snap["memory"]["filter_text"] == WATER_IGNORE
    assert snap["llm"]["output"]["filter_text"].startswith("downweight")
    assert snap["example"]["message"] == "Next: sigh shift"
    snap = session.play("open.sigh.torso")
    assert snap["last_step"]["kind"] == "filtered"
    assert snap["example"]["state"] == "guiding"
    assert snap["example"]["message"] == "Next: scratch left calf"
    assert _highlight(snap)["choice_id"] == "open.scratch.left_calf"
    assert "open.scratch.left_calf" in snap["enabled_choices"]
    assert snap["window"]["open"] is False
    snap = session.play("open.scratch.left_calf")
    assert snap["example"]["state"] == "finished"
    assert snap["last_step"]["kind"] == "pass_a"
    assert_snapshot_legal(snap)


def test_E10_walk_unit_advances_only_on_script():
    walk = ExampleWalk()
    walk.start()
    walk.note("play", "open.sigh.torso")
    walk.note("play", "follow.leave.plus1")
    assert walk.state == "guiding"
    assert walk.step == 2
    walk.note("play", "open.scratch.left_calf")
    assert walk.state == "left"
    walk.note("play", "open.sigh.torso")
    assert walk.state == "left"
    assert walk.step == 2


def test_E11_walk_unit_finishes_on_last_scripted_click():
    walk = ExampleWalk()
    walk.start()
    for item in SCRIPT:
        if item[0] == "play":
            walk.note("play", item[1])
        else:
            walk.note(item[0])
    view = walk.view()
    assert view["state"] == "finished"
    assert view["message"] == FINISHED_MESSAGE
    assert view["highlight"]["list_index"] == -1
