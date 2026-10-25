from nightguard.events import make_event
from nightguard.loop import NightLoop
from nightguard.memory import (
    MemoryStore,
    apply_morning_label,
    contains_disease_word,
    render_memory_text,
)
from tests.helpers import seed_card


def test_M1_recent_five_include_later_not_weight():
    cards = [
        seed_card(night_id="n1", t="01:00:00", outcome_15min="settled_lie"),
        seed_card(night_id="n1", t="02:00:00", outcome_15min="sat_up"),
        seed_card(night_id="n2", t="01:00:00", outcome_15min="left_bed"),
        seed_card(night_id="n2", t="03:00:00", outcome_15min="scratch_again_after_5m"),
        seed_card(night_id="n3", t="01:00:00", outcome_15min="settled_lie"),
        seed_card(night_id="n3", t="04:00:00", outcome_15min="no_new_event"),
    ]
    text, _ = render_memory_text(cards, current_event=make_event(t="04:10:00"))
    assert text.count("\n") + 1 >= 5
    card_lines = [ln for ln in text.splitlines() if not ln.startswith("habit:")]
    assert len(card_lines) == 5
    assert "n1 01:00" not in text
    assert "outcome_15min:" in text
    assert "weight" not in text


def test_M2_uncertain_counted_not_listed():
    cards = [
        seed_card(t="01:00:00", verdict="inconclusive", morning_label="none"),
        seed_card(t="01:10:00", verdict="inconclusive", morning_label="none"),
        seed_card(t="01:20:00", verdict="inconclusive", morning_label="none"),
    ]
    text, count = render_memory_text(cards)
    assert count == 3
    assert "01:00" not in text
    assert "01:10" not in text
    assert "01:20" not in text


def test_M3_clock_cluster_uses_arc_not_string_sort():
    cards = [
        seed_card(night_id="n1", t="01:55:00", outcome_15min="left_bed"),
        seed_card(night_id="n2", t="02:00:00", outcome_15min="left_bed"),
        seed_card(night_id="n3", t="02:15:00", outcome_15min="left_bed"),
    ]
    text, _ = render_memory_text(cards, current_event=make_event(t="02:10:00"))
    assert "habit: ~02:00 outcome_15min=left_bed x3" in text
    assert "motion_counts: sigh_shift x3" in text


def test_M9_midnight_wrap_cluster():
    cards = [
        seed_card(night_id="n1", t="23:40:00", outcome_15min="left_bed"),
        seed_card(night_id="n2", t="23:55:00", outcome_15min="left_bed"),
        seed_card(night_id="n3", t="00:10:00", outcome_15min="left_bed"),
    ]
    text, _ = render_memory_text(cards, current_event=make_event(t="23:50:00"))
    habit = [ln for ln in text.splitlines() if ln.startswith("habit:") and "outcome_15min=left_bed" in ln]
    assert len(habit) == 1
    assert "~23:55" in habit[0]
    assert "x3" in habit[0]
    assert "motion_counts: sigh_shift x3" in habit[0]


def test_M4_clock_habit_hidden_outside_band():
    cards = [
        seed_card(night_id="n1", t="01:55:00", outcome_15min="left_bed"),
        seed_card(night_id="n2", t="02:00:00", outcome_15min="left_bed"),
        seed_card(night_id="n3", t="02:15:00", outcome_15min="left_bed"),
    ]
    text, _ = render_memory_text(cards, current_event=make_event(t="04:00:00"))
    assert "habit: ~02:00 outcome_15min=left_bed" not in text


def test_M5_clock_habit_shown_inside_band():
    cards = [
        seed_card(night_id="n1", t="01:55:00", outcome_15min="left_bed"),
        seed_card(night_id="n2", t="02:00:00", outcome_15min="left_bed"),
        seed_card(night_id="n3", t="02:15:00", outcome_15min="left_bed"),
    ]
    text, _ = render_memory_text(cards, current_event=make_event(t="02:10:00"))
    assert "habit: ~02:00 outcome_15min=left_bed x3" in text


def test_M5b_clock_habit_counts_each_act():
    cards = [
        seed_card(night_id="n1", t="01:55:00", motion_type="curl", outcome_15min="left_bed"),
        seed_card(night_id="n2", t="02:00:00", motion_type="sigh_shift", outcome_15min="left_bed"),
        seed_card(night_id="n3", t="02:15:00", motion_type="sigh_shift", outcome_15min="left_bed"),
    ]
    text, _ = render_memory_text(cards, current_event=make_event(t="02:10:00"))
    assert "motion_counts: curl x1, sigh_shift x2" in text


def test_M6_morning_habit_no_disease_words():
    cards = [
        seed_card(night_id="n1", t="01:00:00", motion_type="scratch_burst", morning_label="not_mosquito"),
        seed_card(night_id="n2", t="01:10:00", motion_type="scratch_burst", morning_label="not_mosquito"),
        seed_card(night_id="n3", t="01:20:00", motion_type="scratch_burst", morning_label="not_mosquito"),
    ]
    text, _ = render_memory_text(cards, current_event=make_event(t="03:00:00"))
    assert "habit: scratch_burst morning not_mosquito x3" in text
    assert contains_disease_word(text) is False


def test_M7_gated_event_does_not_add_card():
    loop = NightLoop()
    loop.on_event(make_event(temp_c=8.0, motion_type="scratch_burst"))
    assert loop.memory.cards == []


def test_M8_morning_mosquito_raises_uncertain_weight():
    store = MemoryStore()
    card = seed_card(verdict="inconclusive", morning_label="none")
    store.add_card(card)
    assert card["weight"] == 0.1
    apply_morning_label(store.cards, card["night_id"], "mosquito")
    assert card["morning_label"] == "mosquito"
    assert card["weight"] == 1.0
