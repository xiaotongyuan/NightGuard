"""Memory cards, weight, habit lines. No disease labels."""

from __future__ import annotations

from collections import defaultdict

from nightguard.clock import circular_median_minutes, clock_arc_min, format_hhmm, minutes_from_midnight
from nightguard.events import hhmm
from nightguard.schema import (
    CARD_KEYS,
    DISEASE_WORDS,
    HABIT_CLOCK_TOLERANCE_MIN,
    HABIT_MIN_COUNT,
)


def card_weight(verdict: str, morning_label: str) -> float:
    if morning_label == "unsure":
        return 0.1
    if morning_label in ("mosquito", "not_mosquito"):
        return 1.0
    if verdict == "inconclusive":
        return 0.1
    return 1.0


def make_card(
    *,
    event: dict,
    pass_a: dict,
    pass_b: dict,
    outcome_15min: str,
    morning_label: str = "none",
    correction_action: dict | None = None,
) -> dict:
    stamp = event["t"][:5].replace(":", "")
    verdict = pass_b["verdict"]
    last = correction_action or pass_a
    card = {
        "card_id": f"{event['night_id']}-{stamp}",
        "night_id": event["night_id"],
        "t": event["t"],
        "motion_type": event["motion_type"],
        "body_zone": event["body_zone"],
        "belief_state": last.get("belief_state", pass_a["belief_state"]),
        "belief_p": last.get("belief_p", pass_a["belief_p"]),
        "light": last["light"],
        "mode": last["mode"],
        "first_light": pass_a["light"],
        "first_mode": pass_a["mode"],
        "correction": "upgraded_on" if correction_action else "none",
        "verdict": verdict,
        "revised_belief_p": pass_b["revised_belief_p"],
        "reason": pass_b["reason"],
        "outcome_15min": outcome_15min,
        "morning_label": morning_label,
        "weight": card_weight(verdict, morning_label),
    }
    return {k: card[k] for k in CARD_KEYS}


def apply_morning_label(cards: list[dict], night_id: str, label: str) -> None:
    for card in cards:
        if card["night_id"] == night_id:
            card["morning_label"] = label
            card["weight"] = card_weight(card["verdict"], label)


def _night_ord(night_id: str) -> int:
    tail = night_id[1:]
    return int(tail) if tail.isdigit() else 0


def high_weight_cards(cards: list[dict]) -> list[dict]:
    return [c for c in cards if c["weight"] == 1.0]


def uncertain_count(cards: list[dict]) -> int:
    return sum(1 for c in cards if c["weight"] == 0.1)


def render_card_line(card: dict) -> str:
    return (
        f"{card['night_id']} {hhmm(card['t'])} | motion_type: {card['motion_type']} "
        f"({card['body_zone']}) | outcome_15min: {card['outcome_15min']} | "
        f"first_light: {card.get('first_light', card['light'])} | "
        f"correction: {card.get('correction', 'none')} | "
        f"response_verdict: {card['verdict']} | morning_label: {card['morning_label']}"
    )


def clock_clusters(cards: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for card in high_weight_cards(cards):
        groups[card["outcome_15min"]].append(card)
    clusters = []
    for outcome, group in groups.items():
        minutes = [minutes_from_midnight(c["t"]) for c in group]
        median = circular_median_minutes(minutes)
        members = [
            c
            for c, m in zip(group, minutes)
            if clock_arc_min(m, median) <= HABIT_CLOCK_TOLERANCE_MIN
        ]
        if len(members) < HABIT_MIN_COUNT:
            continue
        clusters.append(
            {
                "outcome": outcome,
                "median": median,
                "members": members,
                "motions": {c["motion_type"] for c in members},
            }
        )
    return clusters


def clock_habit_lines(clusters: list[dict], current_event: dict | None) -> list[str]:
    lines = []
    for cluster in clusters:
        if current_event is not None:
            if clock_arc_min(current_event["t"], cluster["median"]) > HABIT_CLOCK_TOLERANCE_MIN:
                continue
        center = format_hhmm(cluster["median"])
        n = len(cluster["members"])
        motion_counts: dict[str, int] = defaultdict(int)
        for card in cluster["members"]:
            motion_counts[card["motion_type"]] += 1
        acts = ", ".join(
            f"{motion} x{count}" for motion, count in sorted(motion_counts.items())
        )
        lines.append(
            f"habit: ~{center} outcome_15min={cluster['outcome']} x{n} | "
            f"motion_counts: {acts} (±30min)"
        )
    return lines


def morning_habit_lines(cards: list[dict]) -> list[str]:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for card in high_weight_cards(cards):
        label = card["morning_label"]
        if label in ("mosquito", "not_mosquito"):
            counts[(card["motion_type"], label)] += 1
    lines = []
    for (motion, label), n in sorted(counts.items()):
        if n >= HABIT_MIN_COUNT:
            lines.append(f"habit: {motion} morning {label} x{n}")
    return lines


def morning_habit_motions(cards: list[dict], label: str = "not_mosquito") -> set[str]:
    counts: dict[str, int] = defaultdict(int)
    for card in high_weight_cards(cards):
        if card["morning_label"] == label:
            counts[card["motion_type"]] += 1
    return {motion for motion, n in counts.items() if n >= HABIT_MIN_COUNT}


def recent_high_weight_cards(cards: list[dict]) -> list[dict]:
    visible = high_weight_cards(cards)
    return sorted(
        visible,
        key=lambda c: (_night_ord(c["night_id"]), c["t"]),
        reverse=True,
    )[:5]


def render_memory_text(
    cards: list[dict],
    current_event: dict | None = None,
) -> tuple[str, int]:
    recent = recent_high_weight_cards(cards)
    card_lines = [render_card_line(c) for c in recent]
    habit_lines = clock_habit_lines(clock_clusters(cards), current_event)
    habit_lines.extend(morning_habit_lines(cards))
    parts = card_lines + habit_lines
    text = "\n".join(parts) if parts else "none"
    return text, uncertain_count(cards)


def contains_disease_word(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in DISEASE_WORDS)


class MemoryStore:
    def __init__(self) -> None:
        self.cards: list[dict] = []

    def add_card(self, card: dict) -> None:
        self.cards.append(card)

    def apply_morning_label(self, night_id: str, label: str) -> None:
        apply_morning_label(self.cards, night_id, label)
