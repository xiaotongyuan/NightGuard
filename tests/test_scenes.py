from nightguard.events import make_event
from nightguard.llm import FakeLLM
from nightguard.loop import NightLoop
from nightguard.memory import contains_disease_word, render_memory_text
from tests.helpers import add_minutes, morning_json, off_pass_a_json, seed_card


def test_C1_first_night_scratch_then_sat_up():
    loop = NightLoop()
    start = "02:15:00"
    loop.on_event(make_event(night_id="n1", t=start, motion_type="scratch_burst"))
    loop.on_event(
        make_event(
            night_id="n1",
            t=add_minutes(start, 12),
            posture="sit",
            motion_type="sit_up",
            human_sound="slap",
        )
    )
    assert loop.pass_a_count == 1
    assert loop.pass_b_count == 1
    assert loop.last_pass_b_input["outcome_15min"] == "sat_up"
    assert len(loop.memory.cards) == 1


def test_C2_morning_label_mosquito():
    loop = NightLoop()
    start = "02:15:00"
    loop.on_event(make_event(night_id="n1", t=start, motion_type="scratch_burst"))
    loop.on_event(
        make_event(
            night_id="n1",
            t=add_minutes(start, 12),
            posture="sit",
            motion_type="sit_up",
            human_sound="slap",
        )
    )
    loop.apply_morning_label("n1", "mosquito")
    card = loop.memory.cards[0]
    assert card["morning_label"] == "mosquito"
    assert card["weight"] == 1.0


def test_C3_three_nights_water_habit_visible_on_fourth():
    loop = NightLoop()
    nights = (("n1", "01:55:00"), ("n2", "02:00:00"), ("n3", "02:15:00"))
    for night_id, t in nights:
        loop.on_event(make_event(night_id=night_id, t=t, motion_type="sigh_shift", body_zone="torso"))
        loop.on_event(
            make_event(
                night_id=night_id,
                t=add_minutes(t, 1),
                motion_type="leave_bed",
                posture="off_bed",
            )
        )
    loop.on_event(make_event(night_id="n4", t="02:10:00", motion_type="sigh_shift", body_zone="torso"))
    text = loop.pass_a_payloads[-1]["memory_text"]
    assert "habit: ~02:00 outcome_15min=left_bed" in text


def test_C4_ignore_sigh_shift_not_scratch():
    loop = NightLoop()
    loop.memory.cards.extend(
        [
            seed_card(night_id="n1", t="01:55:00", motion_type="sigh_shift", outcome_15min="left_bed"),
            seed_card(night_id="n2", t="02:00:00", motion_type="sigh_shift", outcome_15min="left_bed"),
            seed_card(night_id="n3", t="02:15:00", motion_type="sigh_shift", outcome_15min="left_bed"),
        ]
    )
    kept = loop.accept_morning_filter("ignore ~01:55-02:15 motion sigh_shift")
    assert kept == "ignore ~01:55-02:15 motion sigh_shift"
    before = loop.pass_a_count
    loop.on_event(make_event(night_id="n4", t="02:10:00", motion_type="sigh_shift", body_zone="torso"))
    assert loop.pass_a_count == before
    loop.on_event(make_event(night_id="n4", t="02:10:00", motion_type="scratch_burst"))
    assert loop.pass_a_count == before + 1


def test_C5_cold_night_like_c1():
    loop = NightLoop()
    start = "02:15:00"
    loop.on_event(make_event(night_id="n1", t=start, temp_c=8.0, motion_type="scratch_burst"))
    loop.on_event(
        make_event(
            night_id="n1",
            t=add_minutes(start, 12),
            temp_c=8.0,
            posture="sit",
            motion_type="sit_up",
            human_sound="slap",
        )
    )
    assert loop.total_llm_calls == 0
    assert loop.memory.cards == []


def test_C6_habitual_scratch_not_a_disease():
    loop = NightLoop()
    nights = ("n1", "n2", "n3")
    for i, night_id in enumerate(nights):
        t = f"01:{10 * i:02d}:00"
        loop.on_event(make_event(night_id=night_id, t=t, motion_type="scratch_burst"))
        loop.advance_clock(f"01:{10 * i + 15:02d}:00")
        loop.apply_morning_label(night_id, "not_mosquito")
    loop.on_event(make_event(night_id="n4", t="03:00:00", motion_type="scratch_burst"))
    text = loop.pass_a_payloads[-1]["memory_text"]
    assert "not_mosquito" in text
    assert contains_disease_word(text) is False
    rendered, _ = render_memory_text(loop.memory.cards, current_event=make_event(t="03:00:00"))
    assert "habit: scratch_burst morning not_mosquito x3" in rendered


def test_C7_three_window_states_off_then_upgrade_then_sit():
    loop = NightLoop(llm=FakeLLM(script=[off_pass_a_json()]))
    start = "02:15:00"
    loop.on_event(make_event(night_id="n1", t=start, motion_type="scratch_burst"))
    assert loop.window.is_open is True
    assert loop.last_pass_a["light"] == "off"
    loop.on_event(
        make_event(
            night_id="n1",
            t=add_minutes(start, 6),
            motion_type="scratch_burst",
            posture="lie_stable",
        )
    )
    assert loop.window.is_open is True
    assert loop.last_action["light"] == "on"
    loop.on_event(
        make_event(
            night_id="n1",
            t=add_minutes(start, 8),
            posture="sit",
            motion_type="sit_up",
            human_sound="slap",
        )
    )
    assert loop.window.is_open is False
    card = loop.memory.cards[0]
    assert card["first_light"] == "off"
    assert card["correction"] == "upgraded_on"
    assert card["light"] == "on"
    assert card["outcome_15min"] == "sat_up"
    text, _ = render_memory_text(loop.memory.cards, current_event=make_event(t="03:00:00"))
    assert "first_light: off" in text
    assert "correction: upgraded_on" in text
    assert "outcome_15min: sat_up" in text


def test_C8_three_water_nights_then_morning_updates_filter():
    loop = NightLoop()
    nights = (("n1", "01:55:00"), ("n2", "02:00:00"), ("n3", "02:15:00"))
    for night_id, t in nights:
        loop.on_event(make_event(night_id=night_id, t=t, motion_type="sigh_shift", body_zone="torso"))
        loop.on_event(
            make_event(
                night_id=night_id,
                t=add_minutes(t, 1),
                motion_type="leave_bed",
                posture="off_bed",
            )
        )
    line = "ignore ~01:55-02:15 motion sigh_shift"
    loop.llm = FakeLLM(script=[morning_json(line)])
    out = loop.run_morning_brief()
    payload = loop.llm.calls[-1][1]
    assert out["filter_text"] == line
    assert "habit:" in payload["habit_text"]
    assert payload["yesterday_filter"] == "none"
    loop.on_event(make_event(night_id="n4", t="02:10:00", motion_type="sigh_shift", body_zone="torso"))
    assert loop.pass_a_count == 0
    loop.on_event(make_event(night_id="n4", t="02:10:00", motion_type="scratch_burst"))
    assert loop.pass_a_count == 1
