"""Pass A / Pass B prompt templates. English only inside the JSON."""

from __future__ import annotations

import json

from nightguard.schema import (
    BELIEF_STATES,
    MODES,
    PASS_A_TRIGGER_MOTIONS,
    VERDICTS,
    WINDOW_MIN,
)


def _one_of(name: str, values: tuple[str, ...]) -> str:
    return f"{name} must be exactly one of: {' | '.join(values)}."


def reply_enums(kind: str) -> str:
    """Every value the model may emit. Local parse has no second LLM."""
    if kind == "pass_a":
        return "\n".join(
            (
                _one_of("belief_state", BELIEF_STATES),
                _one_of("mode", MODES),
                "Do not invent other enum values.",
            )
        )
    if kind == "morning":
        return "\n".join(
            (
                "filter_text must be none or opcode lines only.",
                "opcodes must be exactly one of: ignore | downweight.",
                _one_of("motion", PASS_A_TRIGGER_MOTIONS),
                "Do not invent other enum values.",
            )
        )
    return "\n".join(
        (
            _one_of("verdict", VERDICTS),
            "Do not invent other enum values.",
        )
    )


MORNING_FILTER_GRAMMAR = """Every non-none filter_text line must exactly match one form:
<opcode> ~HH:MM-HH:MM motion <motion_enum>
<opcode> motion <motion_enum>
opcode must be exactly ignore or downweight. motion_enum must be exactly scratch_burst, curl, or sigh_shift.
The word motion is literal and required. Replace both angle-bracket placeholders; do not output angle brackets or vertical bars."""


PASS_A_SYSTEM = f"""TASK
Choose the least disruptive lamp response to the current human motion. The human is the sensor; the input does not detect a mosquito. Do not diagnose.

INPUT SEMANTICS
- motion_type, body_zone, amp, duration_s, centroid_shift, human_sound, and posture describe the person's current motion.
- rain_mm_24h and humidity are weak context, never hard gates.
- memory_text contains recent cards and aggregate habits. A card has rendered labels motion_type, outcome_15min, first_light, correction, response_verdict, and morning_label.
- A clock habit includes motion_counts. Apply it only near that clock and only to a motion named in that habit.
- uncertain_count counts hidden low-weight cards. It is not positive evidence of harassment.
- active_filter is already matched by code. Execute it; do not invent or reinterpret an opcode.

STATE AND ACTION SEMANTICS
- quiet: ordinary low-intensity motion; light off.
- routine_wake: an ordinary personal wake/left-bed routine; mode none.
- possible_harassment: continued harassment is plausible; this is the only state that may use a light-on mode.
- general_discomfort: repeated curl suggests general discomfort, without a diagnosis; use only for curl when uncertain_count >= 3; mode none.
- silent_confirm: first low-disruption check, very_low brightness for 4 seconds.
- assist_search: stronger help after the same motion was too_weak, medium brightness for 6 seconds.
- belief_p is P(continued harassment), from 0.0 to 1.0.

DECISION POLICY AND PRECEDENCE
1. Evidence applies only to the same motion_type. Never transfer evidence from another act.
2. A same-motion morning_label not_mosquito is strongest negative feedback: mode none and belief_p <= 0.35.
3. A same-motion morning_label mosquito is positive feedback: possible_harassment, light-on mode, belief_p >= 0.5.
4. A clock left_bed habit is an ordinary personal routine only for a motion whose own count is at least 3: use quiet or routine_wake and mode none near that clock. A response_verdict of too_strong does not turn this routine into harassment.
5. Without same-motion memory: scratch_burst is direct but inconclusive evidence, so use possible_harassment with silent_confirm; sigh_shift and curl are ordinary and use mode none, except the repeated-curl rule above.
6. Use assist_search only when a card for this same motion_type says response_verdict too_weak and the final decision keeps a light-on mode. A habit line alone never authorizes assist_search.
7. A matched downweight filter caps belief_p at 0.3 and forbids assist_search. It does not itself force mode none. If it conflicts with morning mosquito, keep possible_harassment and silent_confirm, but the 0.3 cap wins.
8. If memory_text is none, assist_search is forbidden.

OUTPUT CONTRACT
Return exactly one flat JSON object, no markdown and no extra keys.
Return exactly reasoning, belief_state, belief_p, and mode. Code derives awake from posture and derives light, brightness, duration_s, and aim from mode and body_zone.
reasoning is one English line and must refer only to the supplied human event and memory.
{reply_enums("pass_a")}"""

PASS_B_SYSTEM = f"""TASK
Review whether the lamp response was appropriate after observing the person's later outcome. Judge the response, not whether a mosquito existed.

INPUT SEMANTICS
- motion_type and posture are the original human event.
- belief_state, belief_p, light, and mode describe the lamp response being reviewed.
- first_light and first_mode preserve the first response for history.
- if correction=upgraded_on, the response being reviewed is the upgraded response in light and mode, not first_light.
- outcome_15min is the primary feedback. later_posture, later_motion_type, and later_human_sound describe the human evidence behind it.

VERDICT SEMANTICS
- appropriate: light off followed by left_bed or settled_lie supports the chosen disturbance level.
- too_strong: light on followed by settled_lie means the response was stronger than needed.
- too_weak: scratch_again_after_5m or sat_up shows that the response was too weak; revised_belief_p >= 0.5.
- inconclusive: no_new_event provides too little evidence to review the response.

DECISION POLICY
- Light off followed by left_bed or settled_lie is appropriate.
- Light on followed by settled_lie is too_strong; revised_belief_p must be lower than the input belief_p.
- scratch_again_after_5m or sat_up is too_weak, including when an upgraded lamp is being reviewed.
- Light on followed by left_bed is genuinely ambiguous. Use the original motion and state; do not force a verdict from left_bed alone.
- revised_belief_p is P(continued harassment) after the later evidence, from 0.0 to 1.0.

OUTPUT CONTRACT
Return exactly one flat JSON object, no markdown and no extra keys.
reason is one English line. It must literally name outcome_15min and at least one supplied later_posture or later_motion_type value.
Do not mention wingbeat or mosquito sound.
{reply_enums("pass_b")}"""

MORNING_SYSTEM = f"""TASK
Compile tomorrow's personal filter from repeated human outcomes. The filter should reduce unnecessary future model calls without hiding plausible harassment. Do not diagnose and do not add or edit hard gates.

INPUT SEMANTICS
- habit_text contains code-counted habits. A clock habit gives its center, outcome_15min, total count, and motion_counts.
- last_night_text contains only last night's cards with rendered labels motion_type, outcome_15min, response_verdict, and morning_label.
- Times in last_night_text are single-episode timestamps for the timeline only. They are not clock habits and cannot supply, center, or bound a timed filter.
- yesterday_filter is the policy currently in force.
- morning_label is the user's label for last night. It is strong feedback, but it does not reveal which unlabeled historical act created a clock habit.

FILTER SEMANTICS
- ignore: this repeated act is ordinary in this context; code skips Pass A, keeps the light off, and writes no card.
- downweight: evidence is mixed; code still runs Pass A, caps belief_p at 0.3, and forbids assist_search.
- none: no justified change.

EVIDENCE AND POLICY
1. Preservation has precedence. If a legal yesterday_filter still matches a qualifying habit and morning_label is none or unsure, copy yesterday_filter exactly. Do not regenerate it, change its opcode or interval, or omit words. Ordinary cards in last_night_text do not authorize a rewrite.
2. Only explicit relevant mosquito or not_mosquito feedback, or a newly qualifying different habit, may justify changing or adding to yesterday_filter.
3. For each new rule, choose the evidence source and rule form before choosing an opcode.
4. A new rule from a clock habit is allowed only when habit_text itself contains a ~HH:MM center and the named motion has a motion_counts count of at least 3. Such a rule MUST be timed and MUST NOT be bare.
5. A new rule from a non-clock habit is allowed only when habit_text explicitly says that motion was morning not_mosquito at least 3 times. Such a rule MUST be bare and MUST NOT be timed.
6. Without either qualifying habit, do not create a new rule. One night, one card, a timestamp in last_night_text, or a motion listed only once cannot create one.
7. Never infer a motion from an outcome. A timed rule may name only a motion explicitly listed in that clock habit's motion_counts.
8. For a new rule, prefer ignore when the same act repeatedly leads to an ordinary outcome and there is no mosquito feedback for that act. Prefer downweight when the clock habit is real but its act counts or recent feedback are mixed.
9. If morning_label is mosquito for the relevant recent act, never ignore that act. Use a timed downweight only when the repeated clock habit still justifies it; otherwise use none.
10. A timed interval must contain the habit center and span 1 to 90 minutes on the shortest clock arc. Near midnight, start may be later than end, such as ~23:30-00:20. Do not replace a qualifying clock rule with a bare rule.

OUTPUT CONTRACT
Return exactly one flat JSON object with brief, timeline, and filter_text; no markdown and no extra keys.
brief and timeline are one English line each and summarize only supplied evidence.
filter_text is none or at most 5 newline-separated opcode lines.
{MORNING_FILTER_GRAMMAR}
{reply_enums("morning")}"""


def morning_input(
    night_id: str,
    habit_text: str,
    last_night_text: str,
    yesterday_filter: str,
    morning_label: str = "none",
) -> dict:
    return {
        "night_id": night_id,
        "habit_text": habit_text or "none",
        "last_night_text": last_night_text or "none",
        "yesterday_filter": yesterday_filter or "none",
        "morning_label": morning_label or "none",
    }


def pass_a_input(event: dict, memory_text: str, uncertain_count: int, active_filter: str) -> dict:
    payload = dict(event)
    payload["window_min"] = WINDOW_MIN
    payload["memory_text"] = memory_text
    payload["uncertain_count"] = uncertain_count
    payload["active_filter"] = active_filter
    return payload


def pass_b_input(pending: dict, outcome_15min: str, later_event: dict | None) -> dict:
    event = pending["event"]
    first = pending["pass_a"]
    judged = pending.get("correction") or first
    later = later_event or {
        "posture": "lie_stable",
        "motion_type": "none",
        "human_sound": "none",
    }
    return {
        "night_id": event["night_id"],
        "t": event["t"],
        "motion_type": event["motion_type"],
        "body_zone": event["body_zone"],
        "posture": event["posture"],
        "belief_state": judged.get("belief_state", first["belief_state"]),
        "belief_p": judged.get("belief_p", first["belief_p"]),
        "light": judged["light"],
        "mode": judged["mode"],
        "first_light": first["light"],
        "first_mode": first["mode"],
        "correction": "upgraded_on" if pending.get("correction") else "none",
        "outcome_15min": outcome_15min,
        "later_posture": later["posture"],
        "later_motion_type": later["motion_type"],
        "later_human_sound": later.get("human_sound", "none"),
    }


def messages(system: str, payload: dict) -> list[dict]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
    ]
