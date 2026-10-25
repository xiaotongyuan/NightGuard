import json

from nightguard.events import make_event
from nightguard.filters import accept_filter_text, first_hit, parse_filter_line
from nightguard.llm import FakeLLM, sanitize_pass_a
from nightguard.loop import NightLoop
from nightguard.memory import clock_clusters, morning_habit_motions, render_memory_text
from tests.helpers import seed_card


def _drink_cluster():
    return [
        seed_card(night_id="n1", t="01:55:00", motion_type="sigh_shift", outcome_15min="left_bed"),
        seed_card(night_id="n2", t="02:00:00", motion_type="sigh_shift", outcome_15min="left_bed"),
        seed_card(night_id="n3", t="02:15:00", motion_type="sigh_shift", outcome_15min="left_bed"),
    ]


def _midnight_cluster():
    return [
        seed_card(night_id="n1", t="23:40:00", motion_type="sigh_shift", outcome_15min="left_bed"),
        seed_card(night_id="n2", t="23:55:00", motion_type="sigh_shift", outcome_15min="left_bed"),
        seed_card(night_id="n3", t="00:10:00", motion_type="sigh_shift", outcome_15min="left_bed"),
    ]


def _accept(raw, cards, yesterday="none"):
    return accept_filter_text(
        raw,
        clock_clusters(cards),
        morning_habit_motions(cards),
        yesterday=yesterday,
    )


def test_F1_accepts_timed_ignore_overlapping_cluster():
    kept = _accept("ignore ~01:55-02:15 motion sigh_shift", _drink_cluster())
    assert kept == "ignore ~01:55-02:15 motion sigh_shift"


def test_F11_extra_spaces_fold_then_match():
    raw = "  ignore  ~01:55-02:15  motion  sigh_shift  "
    kept = _accept(raw, _drink_cluster())
    assert kept == "ignore ~01:55-02:15 motion sigh_shift"


def test_F12_midnight_wrap_is_sixty_not_negative():
    parsed = parse_filter_line("ignore ~23:30-00:30 motion sigh_shift")
    assert parsed is not None
    assert parsed["span"] == 60
    kept = _accept("ignore ~23:30-00:30 motion sigh_shift", _midnight_cluster())
    assert kept == "ignore ~23:30-00:30 motion sigh_shift"


def test_F13_reversed_ends_same_band_as_f1():
    a = parse_filter_line("ignore ~01:55-02:15 motion sigh_shift")
    b = parse_filter_line("ignore ~02:15-01:55 motion sigh_shift")
    assert a is not None and b is not None
    assert a["span"] == b["span"] == 20
    kept = _accept("ignore ~02:15-01:55 motion sigh_shift", _drink_cluster())
    assert kept == "ignore ~02:15-01:55 motion sigh_shift"


def test_F14_comma_is_rejected():
    assert parse_filter_line("ignore ~01:55-02:15, motion sigh_shift") is None
    kept = _accept("ignore ~01:55-02:15, motion sigh_shift", _drink_cluster(), yesterday="none")
    assert kept == "none"


def test_F15_arc_over_90_rejected():
    assert parse_filter_line("ignore ~22:00-00:30 motion sigh_shift") is None


def test_F2_motion_not_in_cluster_dropped():
    kept = _accept("ignore ~01:55-02:15 motion scratch_burst", _drink_cluster())
    assert kept == "none"


def test_F3_span_over_90_dropped():
    assert parse_filter_line("ignore ~01:00-03:00 motion sigh_shift") is None


def test_F4_unknown_opcode_dropped():
    assert parse_filter_line("suppress ~01:55-02:15 motion sigh_shift") is None


def test_F5_keeps_only_legal_middle_line():
    raw = "\n".join(
        [
            "suppress ~01:55-02:15 motion sigh_shift",
            "ignore ~01:55-02:15 motion sigh_shift",
            "ignore ~01:00-04:00 motion sigh_shift",
        ]
    )
    kept = _accept(raw, _drink_cluster())
    assert kept == "ignore ~01:55-02:15 motion sigh_shift"


def test_F6_all_illegal_keeps_yesterday():
    kept = _accept("suppress everything", _drink_cluster(), yesterday="ignore ~01:55-02:15 motion sigh_shift")
    assert kept == "ignore ~01:55-02:15 motion sigh_shift"


def test_F7_first_matching_line_wins_ignore():
    text = "ignore ~01:55-02:15 motion sigh_shift\ndownweight ~01:55-02:15 motion sigh_shift"
    event = make_event(t="02:10:00", motion_type="sigh_shift")
    hit = first_hit(text, event)
    assert hit is not None
    assert hit["opcode"] == "ignore"
    loop = NightLoop()
    loop.memory.cards.extend(_drink_cluster())
    loop.filter_text = text
    before = loop.pass_a_count
    loop.on_event(event)
    assert loop.pass_a_count == before
    assert loop.last_pass_a["light"] == "off"


def test_F8_downweight_still_pass_a_and_clamped():
    line = "downweight ~01:55-02:15 motion sigh_shift"
    event = make_event(t="02:10:00", motion_type="sigh_shift", body_zone="torso")
    raw = json.dumps(
        {
            "reasoning": "High belief wrongly.",
            "belief_state": "possible_harassment",
            "belief_p": 0.9,
            "mode": "assist_search",
        }
    )
    loop = NightLoop(llm=FakeLLM(script=[raw]))
    loop.memory.cards.extend(_drink_cluster())
    loop.filter_text = line
    out = loop.on_event(event)
    assert loop.pass_a_count == 1
    assert loop.pass_a_payloads[-1]["active_filter"] == line
    assert out["belief_p"] <= 0.3
    assert out["mode"] != "assist_search"
    cleaned = sanitize_pass_a(event, json.loads(raw), line)
    assert cleaned["belief_p"] <= 0.3
    assert cleaned["mode"] != "assist_search"


def test_F9_drop_is_rejected_and_memory_stays_visible():
    cards = _drink_cluster()
    line = "drop ~01:55-02:15 motion sigh_shift"
    text, _ = render_memory_text(cards, current_event=make_event(t="02:10:00"))
    assert parse_filter_line(line) is None
    assert "motion_type: sigh_shift" in text
    assert len(cards) == 3


def test_F10_bare_ignore_needs_not_mosquito_habit():
    cards = _drink_cluster()
    kept = _accept("ignore motion scratch_burst", cards)
    assert kept == "none"
