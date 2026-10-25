from nightguard.events import make_event
from nightguard.llm import FakeLLM
from nightguard.loop import NightLoop
from tests.helpers import add_minutes, off_pass_a_json


def test_L1_one_scratch_then_timeout():
    loop = NightLoop()
    start = "02:15:00"
    loop.on_event(make_event(t=start, motion_type="scratch_burst"))
    assert loop.pass_a_count == 1
    loop.advance_clock(add_minutes(start, 15))
    assert loop.pass_a_count == 1
    assert loop.pass_b_count == 1
    assert loop.memory.cards[0]["outcome_15min"] == "no_new_event"
    assert loop.total_llm_calls == 2


def test_L2_sit_one_minute_later_is_sat_up_not_second_pass_a():
    loop = NightLoop()
    start = "02:15:00"
    loop.on_event(make_event(t=start, motion_type="scratch_burst"))
    loop.on_event(
        make_event(
            t=add_minutes(start, 1),
            posture="sit",
            motion_type="sit_up",
            human_sound="slap",
        )
    )
    assert loop.pass_a_count == 1
    assert loop.pass_b_count == 1
    assert loop.last_pass_b_input["outcome_15min"] == "sat_up"


def test_L3_budget_is_three_pairs_not_seven_pass_a():
    loop = NightLoop()
    hour = 1
    for _ in range(3):
        t = f"{hour:02d}:00:00"
        loop.on_event(make_event(t=t, motion_type="scratch_burst"))
        loop.on_event(
            make_event(
                t=f"{hour:02d}:01:00",
                posture="sit",
                motion_type="sit_up",
            )
        )
        hour += 1
    assert loop.pass_a_count == 3
    assert loop.pass_b_count == 3
    assert loop.llm_calls_tonight == 6
    loop.on_event(make_event(t="04:00:00", motion_type="scratch_burst"))
    assert loop.pass_a_count == 3
    assert "budget" in loop.last_pass_a["reasoning"]


def test_S9_first_off_then_scratch_upgrades_and_keeps_window():
    loop = NightLoop(llm=FakeLLM(script=[off_pass_a_json()]))
    start = "02:00:00"
    loop.on_event(make_event(t=start, motion_type="scratch_burst"))
    calls_before = loop.total_llm_calls
    out = loop.on_event(
        make_event(t=add_minutes(start, 6), motion_type="scratch_burst", posture="lie_stable")
    )
    assert loop.window.is_open is True
    assert loop.pass_b_count == 0
    assert loop.total_llm_calls == calls_before
    assert out["light"] == "on"
    assert out["mode"] == "assist_search"
    assert loop.last_action["light"] == "on"


def test_S10_after_upgrade_sit_closes_and_records_chain():
    loop = NightLoop(llm=FakeLLM(script=[off_pass_a_json()]))
    start = "02:00:00"
    loop.on_event(make_event(t=start, motion_type="scratch_burst"))
    loop.on_event(make_event(t=add_minutes(start, 6), motion_type="scratch_burst", posture="lie_stable"))
    loop.on_event(make_event(t=add_minutes(start, 7), posture="sit", motion_type="sit_up"))
    assert loop.window.is_open is False
    assert loop.pass_b_count == 1
    card = loop.memory.cards[0]
    assert card["first_light"] == "off"
    assert card["correction"] == "upgraded_on"
    assert card["light"] == "on"
    assert loop.last_pass_b_input["correction"] == "upgraded_on"
    assert loop.last_pass_b_input["light"] == "on"


def test_S11_second_confirm_after_upgrade_closes_without_another_light():
    loop = NightLoop(llm=FakeLLM(script=[off_pass_a_json()]))
    start = "02:00:00"
    loop.on_event(make_event(t=start, motion_type="scratch_burst"))
    loop.on_event(make_event(t=add_minutes(start, 6), motion_type="scratch_burst", posture="lie_stable"))
    action_after_upgrade = dict(loop.last_action)
    loop.on_event(
        make_event(t=add_minutes(start, 12), motion_type="scratch_burst", posture="lie_stable")
    )
    assert loop.window.is_open is False
    assert loop.last_pass_b_input["outcome_15min"] == "scratch_again_after_5m"
    assert loop.last_action == action_after_upgrade
    assert loop.memory.cards[0]["correction"] == "upgraded_on"


def test_S12_first_off_then_quiet_timeout_does_not_upgrade():
    loop = NightLoop(llm=FakeLLM(script=[off_pass_a_json()]))
    start = "02:00:00"
    loop.on_event(make_event(t=start, motion_type="scratch_burst"))
    loop.advance_clock(add_minutes(start, 15))
    assert loop.pass_b_count == 1
    card = loop.memory.cards[0]
    assert card["correction"] == "none"
    assert card["first_light"] == "off"
    assert card["light"] == "off"


def test_S13_first_on_then_scratch_closes_without_third_round():
    loop = NightLoop()
    start = "02:00:00"
    loop.on_event(make_event(t=start, motion_type="scratch_burst"))
    assert loop.last_pass_a["light"] == "on"
    loop.on_event(make_event(t=add_minutes(start, 6), motion_type="scratch_burst", posture="lie_stable"))
    assert loop.window.is_open is False
    assert loop.pass_b_count == 1
    assert loop.last_pass_b_input["outcome_15min"] == "scratch_again_after_5m"
    assert loop.memory.cards[0]["correction"] == "none"


def test_S14_first_on_then_settled_lie_does_not_rewatch():
    loop = NightLoop()
    start = "02:00:00"
    loop.on_event(make_event(t=start, motion_type="scratch_burst"))
    assert loop.last_pass_a["light"] == "on"
    loop.advance_clock(add_minutes(start, 15))
    assert loop.window.is_open is False
    card = loop.memory.cards[0]
    assert card["correction"] == "none"
    assert card["light"] == "on"
    assert card["first_light"] == "on"


def test_S15_after_upgrade_leave_bed_closes_judging_second_light():
    loop = NightLoop(llm=FakeLLM(script=[off_pass_a_json()]))
    start = "02:00:00"
    loop.on_event(make_event(t=start, motion_type="scratch_burst"))
    loop.on_event(make_event(t=add_minutes(start, 6), motion_type="scratch_burst", posture="lie_stable"))
    loop.on_event(
        make_event(t=add_minutes(start, 7), motion_type="leave_bed", posture="off_bed")
    )
    assert loop.window.is_open is False
    assert loop.last_pass_b_input["outcome_15min"] == "left_bed"
    card = loop.memory.cards[0]
    assert card["correction"] == "upgraded_on"
    assert card["light"] == "on"
    assert card["first_light"] == "off"


def test_S16_after_upgrade_timeout_closes_without_another_light():
    loop = NightLoop(llm=FakeLLM(script=[off_pass_a_json()]))
    start = "02:00:00"
    loop.on_event(make_event(t=start, motion_type="scratch_burst"))
    loop.on_event(make_event(t=add_minutes(start, 6), motion_type="scratch_burst", posture="lie_stable"))
    action_after_upgrade = dict(loop.last_action)
    loop.advance_clock(add_minutes(start, 21))
    assert loop.window.is_open is False
    assert loop.pass_b_count == 1
    assert loop.last_action == action_after_upgrade
    assert loop.memory.cards[0]["correction"] == "upgraded_on"


def test_S17_first_off_then_early_sit_does_not_upgrade():
    loop = NightLoop(llm=FakeLLM(script=[off_pass_a_json()]))
    start = "02:00:00"
    loop.on_event(make_event(t=start, motion_type="scratch_burst"))
    loop.on_event(make_event(t=add_minutes(start, 1), posture="sit", motion_type="sit_up"))
    assert loop.window.is_open is False
    assert loop.last_pass_b_input["outcome_15min"] == "sat_up"
    card = loop.memory.cards[0]
    assert card["correction"] == "none"
    assert card["light"] == "off"
    leave = NightLoop(llm=FakeLLM(script=[off_pass_a_json()]))
    leave.on_event(make_event(t=start, motion_type="scratch_burst"))
    leave.on_event(make_event(t=add_minutes(start, 1), motion_type="leave_bed", posture="off_bed"))
    assert leave.last_pass_b_input["outcome_15min"] == "left_bed"
    assert leave.memory.cards[0]["correction"] == "none"


def test_L4_cold_room_never_calls_llm():
    loop = NightLoop()
    loop.on_event(make_event(temp_c=8.0, motion_type="scratch_burst"))
    assert loop.total_llm_calls == 0
    assert loop.pass_a_count == 0
    assert loop.memory.cards == []


def test_L5_upgrade_does_not_spend_llm_budget():
    loop = NightLoop(llm=FakeLLM(script=[off_pass_a_json()]))
    start = "02:00:00"
    loop.on_event(make_event(t=start, motion_type="scratch_burst"))
    loop.on_event(make_event(t=add_minutes(start, 6), motion_type="scratch_burst", posture="lie_stable"))
    loop.on_event(make_event(t=add_minutes(start, 7), posture="sit", motion_type="sit_up"))
    assert loop.pass_a_count == 1
    assert loop.pass_b_count == 1
    assert loop.total_llm_calls == 2
