"""Morning filter updates from memory and yesterday_filter. FakeLLM only."""

from nightguard.events import make_event
from nightguard.llm import FakeLLM
from nightguard.loop import NightLoop
from tests.helpers import morning_json, seed_card

WATER_LINE = "ignore ~01:55-02:15 motion sigh_shift"
WATER_DOWN = "downweight ~01:55-02:15 motion sigh_shift"


def _water_cards() -> list[dict]:
    return [
        seed_card(night_id="n1", t="01:55:00", motion_type="sigh_shift", outcome_15min="left_bed"),
        seed_card(night_id="n2", t="02:00:00", motion_type="sigh_shift", outcome_15min="left_bed"),
        seed_card(night_id="n3", t="02:15:00", motion_type="sigh_shift", outcome_15min="left_bed"),
    ]


def _last_morning_payload(loop: NightLoop) -> dict:
    morning_calls = [payload for kind, payload in loop.llm.calls if kind == "morning"]
    assert morning_calls
    return morning_calls[-1]


def test_U0_morning_payload_has_yesterday_filter_and_habit():
    loop = NightLoop()
    loop.memory.cards.extend(_water_cards())
    loop.filter_text = WATER_LINE
    loop.current_night = "n4"
    loop.run_morning_brief()
    payload = _last_morning_payload(loop)
    assert set(payload) >= {"habit_text", "last_night_text", "yesterday_filter", "morning_label"}
    assert payload["yesterday_filter"] == WATER_LINE
    assert "habit:" in payload["habit_text"]
    assert payload["morning_label"] == "none"


def test_U1_no_cards_none_stays_none():
    loop = NightLoop()
    loop.run_morning_brief()
    assert loop.filter_text == "none"
    assert _last_morning_payload(loop)["yesterday_filter"] == "none"


def test_U2_no_new_habit_copies_yesterday():
    loop = NightLoop()
    loop.filter_text = WATER_LINE
    loop.run_morning_brief()
    assert loop.filter_text == WATER_LINE
    assert _last_morning_payload(loop)["yesterday_filter"] == WATER_LINE


def test_U3_new_cluster_accepts_ignore_and_skips_sigh():
    loop = NightLoop(llm=FakeLLM(script=[morning_json(WATER_LINE)]))
    loop.memory.cards.extend(_water_cards())
    loop.current_night = "n4"
    out = loop.run_morning_brief()
    assert out["filter_text"] == WATER_LINE
    before = loop.pass_a_count
    loop.on_event(make_event(night_id="n4", t="02:10:00", motion_type="sigh_shift", body_zone="torso"))
    assert loop.pass_a_count == before


def test_U4_existing_ignore_is_not_replaced_by_unknown_motion():
    loop = NightLoop()
    loop.memory.cards.extend(_water_cards())
    loop.filter_text = WATER_LINE
    loop.current_night = "n4"
    loop.run_morning_brief()
    assert loop.filter_text == WATER_LINE
    assert "scratch_burst" not in loop.filter_text
    assert loop.filter_text.count("\n") == 0


def test_U5_illegal_line_keeps_yesterday():
    loop = NightLoop(llm=FakeLLM(script=[morning_json("ignore ~01:55-02:15, motion sigh_shift")]))
    loop.memory.cards.extend(_water_cards())
    loop.filter_text = WATER_LINE
    loop.current_night = "n4"
    loop.run_morning_brief()
    assert loop.filter_text == WATER_LINE


def test_U6_model_may_keep_yesterday_and_add_downweight():
    both = WATER_LINE + "\n" + WATER_DOWN
    loop = NightLoop(llm=FakeLLM(script=[morning_json(both)]))
    loop.memory.cards.extend(_water_cards())
    loop.filter_text = WATER_LINE
    loop.current_night = "n4"
    loop.run_morning_brief()
    assert loop.filter_text.splitlines() == [WATER_LINE, WATER_DOWN]
    before = loop.pass_a_count
    loop.on_event(make_event(night_id="n4", t="02:10:00", motion_type="sigh_shift", body_zone="torso"))
    assert loop.pass_a_count == before


def test_U7_bare_ignore_needs_not_mosquito_habit_and_label_in_payload():
    line = "ignore motion scratch_burst"
    loop = NightLoop(llm=FakeLLM(script=[morning_json(line)]))
    loop.memory.cards.extend(
        [
            seed_card(
                night_id=night,
                t="01:10:00",
                motion_type="scratch_burst",
                body_zone="left_calf",
                morning_label="not_mosquito",
            )
            for night in ("n1", "n2", "n3")
        ]
    )
    loop.current_night = "n4"
    out = loop.run_morning_brief(morning_label="not_mosquito")
    assert _last_morning_payload(loop)["morning_label"] == "not_mosquito"
    assert out["filter_text"] == line
