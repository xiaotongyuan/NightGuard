"""UiSession tests. No browser. No remote LLM."""

import pytest

from nightguard.llm import FakeLLM
from nightguard.schema import FORBIDDEN_LLM_KEYS
from nightguard.ui_session import FOLLOW_CHOICES, OPEN_CHOICES, UiError, UiSession
from tests.helpers import seed_card

WATER = "ignore ~01:55-02:15 motion sigh_shift"
WATER_DOWN = "downweight ~01:55-02:15 motion sigh_shift"


def _water_cards():
    return [
        seed_card(night_id="n1", t="01:55:00", motion_type="sigh_shift", outcome_15min="left_bed"),
        seed_card(night_id="n2", t="02:00:00", motion_type="sigh_shift", outcome_15min="left_bed"),
        seed_card(night_id="n3", t="02:15:00", motion_type="sigh_shift", outcome_15min="left_bed"),
    ]


def _open_off(temp=26.4, fixture="off"):
    session = UiSession(mode="inspect", temp_c=temp, pass_a_fixture=fixture)
    return session, session.play("open.scratch.left_calf")


def test_backend_label_is_nano_until_usage_runs_out():
    from nightguard.adapter import RemoteLLM
    from nightguard.ui_session import backend_label

    llm = RemoteLLM(
        provider="nemotron",
        api_key="x",
        model="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        base_url="https://example.invalid/v1",
    )
    assert backend_label(llm) == "nano"
    session = UiSession(llm=llm)
    assert session.snapshot()["llm_backend"] == "nano"
    llm.out_of_usage = True
    assert session.snapshot()["llm_backend"] == "out of usage"


def test_W1_new_session_closed_only_openers():
    snap = UiSession().snapshot()
    assert snap["window"]["phase"] == "closed"
    assert set(snap["enabled_choices"]) == set(OPEN_CHOICES)
    assert set(snap["disabled_choices"]) == set(FOLLOW_CHOICES)
    assert snap["action"]["light"] == "off"
    assert snap["last_step"]["llm_parse_failed"] is False
    assert snap["llm"]["input"] is None
    assert snap["llm"]["remote"] is None
    assert snap["llm_backend"] == "fake"


def test_W2_open_scratch_off_enters_watch():
    _session, snap = _open_off()
    assert snap["last_step"]["kind"] == "pass_a"
    assert snap["last_step"]["llm_called"] is True
    assert snap["last_step"]["llm_parse_failed"] is False
    assert snap["window"]["phase"] == "watch"
    assert set(snap["enabled_choices"]) == set(FOLLOW_CHOICES)
    assert not any(c.startswith("open.") for c in snap["enabled_choices"])


def test_snapshot_marks_llm_parse_failed_after_bad_json():
    session = UiSession(mode="continue", llm=FakeLLM(script=["{", "{"]))
    snap = session.play("open.scratch.left_calf")
    assert snap["last_step"]["kind"] == "pass_a"
    assert snap["last_step"]["llm_called"] is True
    assert snap["last_step"]["llm_parse_failed"] is True
    assert str(snap["llm"]["output"]["reasoning"]).startswith("parse_failed")


def test_W3_cold_room_gates():
    session, snap = _open_off(temp=8)
    assert snap["last_step"]["kind"] == "gated"
    assert snap["last_step"]["llm_called"] is False
    assert snap["last_step"]["gate_hit"] == "temp"
    assert any(r["id"] == "temp" and r["hit"] for r in snap["rules"]["hard"])
    assert snap["window"]["phase"] == "closed"
    assert set(snap["enabled_choices"]) == set(OPEN_CHOICES)


def test_W19_lie_down_after_close_turns_lamp_off():
    session = UiSession(mode="continue", pass_a_fixture="on")
    session.play("open.scratch.left_calf")
    session.play("follow.sit.plus1")
    assert session.snapshot()["action"]["light"] == "on"
    snap = session.play("open.lie")
    assert snap["last_step"]["kind"] == "gated"
    assert snap["last_step"]["llm_called"] is False
    assert snap["last_step"]["gate_hit"] == "settle"
    assert snap["action"]["light"] == "off"
    assert snap["person"]["posture"] == "lie_stable"


def test_W15_open_while_window_open_rejected():
    session = UiSession(mode="continue", pass_a_fixture="off")
    session.play("open.scratch.left_calf")
    with pytest.raises(UiError) as exc:
        session.play("open.scratch.head")
    assert exc.value.code == "choice_disabled"
    assert session.loop.window.is_open is True


def test_W16_follow_while_closed_rejected():
    session = UiSession()
    with pytest.raises(UiError) as exc:
        session.play("follow.scratch.plus2")
    assert exc.value.code == "choice_disabled"


def test_W17_inspect_reopen_resets_count():
    session = UiSession(pass_a_fixture="off")
    session.play("open.scratch.head")
    snap = session.play("open.scratch.head")
    assert snap["budget"]["pass_a_count"] == 1


def test_W18_continue_accumulates_after_close():
    session = UiSession(mode="continue", pass_a_fixture="off")
    session.play("open.scratch.left_calf")
    session.play("follow.sit.plus1")
    snap = session.play("open.scratch.head")
    assert snap["budget"]["pass_a_count"] == 2


def test_W4_plus2_stays_watch():
    session, _ = _open_off()
    snap = session.play("follow.scratch.plus2")
    assert snap["window"]["phase"] == "watch"
    assert snap["last_step"]["kind"] == "follow"
    assert snap["last_step"]["llm_called"] is False
    assert "follow.scratch.plus2" in snap["enabled_choices"]
    assert "follow.scratch.plus6" in snap["enabled_choices"]


def test_W5_plus6_after_off_upgrades():
    session, _ = _open_off()
    snap = session.play("follow.scratch.plus6")
    assert snap["window"]["phase"] == "upgraded"
    assert snap["last_step"]["kind"] == "upgrade"
    assert snap["action"]["light"] == "on"
    assert snap["last_step"]["llm_called"] is False
    assert snap["last_step"]["correction"] == "upgraded_on"
    assert snap["llm"]["output"] is not None
    assert snap["llm"]["output"]["light"] == "off"
    assert set(snap["enabled_choices"]) == set(FOLLOW_CHOICES)


def test_W6_upgrade_then_sit_closes():
    session, _ = _open_off()
    session.play("follow.scratch.plus6")
    snap = session.play("follow.sit.plus1")
    assert snap["window"]["phase"] == "closed"
    assert snap["last_step"]["kind"] == "pass_b"
    assert session.loop.memory.cards[0]["correction"] == "upgraded_on"
    assert set(snap["enabled_choices"]) == set(OPEN_CHOICES)
    assert set(snap["disabled_choices"]) == set(FOLLOW_CHOICES)


def test_W7_second_plus6_closes_without_relight():
    session, _ = _open_off()
    up = session.play("follow.scratch.plus6")
    snap = session.play("follow.scratch.plus6")
    assert snap["window"]["phase"] == "closed"
    assert snap["last_step"]["kind"] == "pass_b"
    assert snap["action"]["aim"] == up["action"]["aim"]
    assert "follow.scratch.plus6" in snap["disabled_choices"]


def test_W8_wait15_after_off():
    session, _ = _open_off()
    snap = session.play("follow.wait15")
    assert snap["window"]["phase"] == "closed"
    assert snap["last_step"]["kind"] == "pass_b"
    assert snap["last_step"]["correction"] == "none"
    assert snap["action"]["light"] == "off"


def test_W9_plus6_after_on_skips_upgrade():
    session, _ = _open_off(fixture="on")
    snap = session.play("follow.scratch.plus6")
    assert snap["window"]["phase"] == "closed"
    assert snap["last_step"]["kind"] == "pass_b"
    assert snap["last_step"]["kind"] != "upgrade"
    assert snap["window"]["phase"] != "upgraded"


def test_W10_wait15_after_on():
    session, _ = _open_off(fixture="on")
    snap = session.play("follow.wait15")
    assert snap["window"]["phase"] == "closed"
    assert snap["last_step"]["correction"] == "none"
    assert snap["action"]["light"] == "on"


def test_W11_upgrade_then_leave():
    session, _ = _open_off()
    session.play("follow.scratch.plus6")
    snap = session.play("follow.leave.plus1")
    assert snap["last_step"]["kind"] == "pass_b"
    assert snap["last_step"]["correction"] == "upgraded_on"


def test_W12_upgrade_then_wait15():
    session, _ = _open_off()
    session.play("follow.scratch.plus6")
    snap = session.play("follow.wait15")
    assert snap["window"]["phase"] == "closed"
    assert snap["last_step"]["correction"] == "upgraded_on"


def test_W13_early_sit_no_upgrade():
    session, _ = _open_off()
    snap = session.play("follow.sit.plus1")
    assert snap["window"]["phase"] == "closed"
    assert snap["last_step"]["correction"] == "none"
    assert snap["last_step"]["kind"] == "pass_b"


def test_W14_on_then_sit_no_second_pass_a():
    session, _ = _open_off(fixture="on")
    snap = session.play("follow.sit.plus1")
    assert snap["window"]["phase"] == "closed"
    assert snap["budget"]["pass_a_count"] == 1


def test_WF0_morning_payload_has_four_keys():
    session = UiSession()
    session.loop.memory.cards.extend(_water_cards())
    session.loop.filter_text = WATER
    snap = session.morning()
    payload = snap["llm"]["input"]
    assert set(payload) >= {"habit_text", "last_night_text", "yesterday_filter", "morning_label"}
    assert "habit:" in payload["habit_text"]


def test_WF1_empty_stays_none():
    snap = UiSession().morning()
    assert snap["memory"]["filter_text"] == "none"
    assert snap["rules"]["soft_diff"] == {"added": [], "removed": [], "kept": []}


def test_WF2_copy_yesterday_without_new_cluster():
    session = UiSession(filter_text=WATER)
    snap = session.morning()
    assert snap["memory"]["filter_text"] == WATER
    assert WATER in snap["rules"]["soft_diff"]["kept"]


def test_WF3_ignore_filters_sigh():
    session = UiSession(pass_a_fixture="off")
    session.loop.memory.cards.extend(_water_cards())
    snap = session.morning(script_filter_text=WATER)
    assert any(row["line"] == WATER for row in snap["rules"]["soft"])
    next_snap = session.play("open.sigh.torso")
    assert next_snap["last_step"]["kind"] == "filtered"
    assert next_snap["last_step"]["llm_called"] is False


def test_WF5_illegal_keeps_yesterday():
    session = UiSession(filter_text=WATER)
    session.loop.memory.cards.extend(_water_cards())
    snap = session.morning(script_filter_text="ignore ~01:55-02:15, motion sigh_shift")
    assert snap["memory"]["filter_text"] == WATER
    assert snap["rules"]["soft_diff"]["added"] == []


def test_WF6_two_legal_lines_first_ignore_wins():
    session = UiSession(filter_text=WATER, pass_a_fixture="off")
    session.loop.memory.cards.extend(_water_cards())
    snap = session.morning(script_filter_text=WATER + "\n" + WATER_DOWN)
    assert [row["line"] for row in snap["rules"]["soft"]] == [WATER, WATER_DOWN]
    next_snap = session.play("open.sigh.torso")
    assert next_snap["last_step"]["kind"] == "filtered"


def test_WF7_bare_ignore_not_mosquito():
    session = UiSession()
    session.loop.memory.cards.extend(
        [
            seed_card(
                night_id=n,
                t="01:10:00",
                motion_type="scratch_burst",
                body_zone="left_calf",
                morning_label="not_mosquito",
            )
            for n in ("n1", "n2", "n3")
        ]
    )
    snap = session.morning(morning_label="not_mosquito", script_filter_text="ignore motion scratch_burst")
    assert snap["memory"]["filter_text"] == "ignore motion scratch_burst"
    assert snap["llm"]["input"]["morning_label"] == "not_mosquito"


def test_WF8_new_legal_line_does_not_merge_yesterday():
    session = UiSession(filter_text=WATER)
    session.loop.memory.cards.extend(_water_cards())
    snap = session.morning(script_filter_text=WATER_DOWN)
    assert snap["memory"]["filter_text"] == WATER_DOWN
    assert WATER in snap["rules"]["soft_diff"]["removed"]
    assert WATER_DOWN in snap["rules"]["soft_diff"]["added"]


def test_WF9_morning_refused_while_open():
    session, _ = _open_off()
    with pytest.raises(UiError) as exc:
        session.morning()
    assert exc.value.code == "window_open"
    assert session.loop.filter_text == "none"
    assert session.night_id == "n1"


def test_WF10_morning_advances_night_keeps_cards_and_llm():
    session = UiSession(filter_text=WATER)
    session.loop.memory.cards.extend(_water_cards())
    snap = session.morning()
    assert snap["night_id"] == "n2"
    assert snap["t"] == "02:00:00"
    assert snap["last_step"]["kind"] == "morning"
    assert snap["llm"]["input"] is not None
    assert snap["llm"]["output"] is not None
    assert snap["memory"]["filter_text"] == WATER
    assert len(session.loop.memory.cards) == 3
    assert snap["budget"]["llm_calls_tonight"] == 0
    assert snap["action"]["light"] == "off"


def test_WF11_morning_stamps_closing_night_then_advances():
    session = UiSession()
    session.loop.memory.cards.append(
        seed_card(night_id="n1", t="02:15:00", motion_type="scratch_burst", verdict="inconclusive")
    )
    snap = session.morning(morning_label="not_mosquito")
    card = session.loop.memory.cards[0]
    assert card["morning_label"] == "not_mosquito"
    assert card["weight"] == 1.0
    assert snap["night_id"] == "n2"
    assert any("morning_label: not_mosquito" in line for line in snap["memory"]["cards"])


def test_W20_mode_next_night_without_morning():
    session = UiSession(filter_text=WATER)
    session.loop.memory.cards.extend(_water_cards())
    snap = session.next_night()
    assert snap["night_id"] == "n2"
    assert snap["last_step"]["kind"] == "none"
    assert snap["llm"]["input"] is None
    assert snap["memory"]["filter_text"] == WATER
    assert len(session.loop.memory.cards) == 3


def test_W21_past_nights_shows_five_newest_high_weight():
    session = UiSession()
    session.loop.memory.cards.extend(
        [
            seed_card(night_id="n1", t="01:00:00"),
            seed_card(night_id="n1", t="02:00:00"),
            seed_card(night_id="n2", t="01:00:00"),
            seed_card(night_id="n2", t="03:00:00"),
            seed_card(night_id="n3", t="01:00:00"),
            seed_card(night_id="n3", t="04:00:00"),
            seed_card(night_id="n3", t="05:00:00", verdict="inconclusive"),
        ]
    )
    snap = session.snapshot()
    assert len(snap["memory"]["cards"]) == 5
    assert snap["memory"]["uncertain_count"] == 1
    assert snap["memory"]["cards"][0].startswith("n3 04:00")
    assert all("weight" not in line for line in snap["memory"]["cards"])
    assert not any("05:00" in line for line in snap["memory"]["cards"])


def test_WR1_mosquito_draw_stays_out_of_event_and_llm():
    session = UiSession(pass_a_fixture="on")
    session.set_ui({"mosquito_draw": "head"})
    snap = session.play("open.scratch.left_calf")
    blob = str(snap)
    assert "mosquito_draw" not in str(snap["llm"])
    for key in FORBIDDEN_LLM_KEYS:
        assert key not in (snap["llm"]["input"] or {})
        assert key not in (snap["llm"]["output"] or {})
    event = session.loop.log.rows[-1]
    assert "mosquito_draw" not in event
    assert "n_mosquitoes" not in blob.split("llm")[1] if "llm" in blob else True


def test_WR2_head_scratch_aims_wall_head():
    session = UiSession(pass_a_fixture="on")
    snap = session.play("open.scratch.head")
    assert snap["action"]["aim"] == "wall_head"
    assert snap["action"]["light"] == "on"


def test_WR3_off_clears_aim():
    session = UiSession(pass_a_fixture="off")
    snap = session.play("open.scratch.head")
    assert snap["action"]["aim"] == "none"
    assert snap["action"]["light"] == "off"


def test_WR4_closed_sit_is_gated():
    session = UiSession()
    snap = session.play("open.sit")
    assert snap["last_step"]["kind"] == "gated"
    assert snap["last_step"]["gate_hit"] == "up"
    assert snap["person"]["posture"] == "sit"
    assert snap["action"]["light"] == "off"
