"""Shared golden payloads. Local FakeLLM and remote Gemini use the same objects."""

from nightguard.events import make_event
from nightguard.prompts import morning_input, pass_a_input, pass_b_input


def sample_pass_a_input() -> dict:
    event = make_event(
        night_id="n2",
        t="03:12:40",
        temp_c=26.4,
        motion_type="scratch_burst",
        body_zone="left_calf",
        posture="lie_stable",
    )
    return pass_a_input(event, "none", 0, "none")


def sample_pass_b_no_new_event() -> dict:
    event = make_event(
        night_id="n2",
        t="03:12:40",
        motion_type="scratch_burst",
        body_zone="left_calf",
        posture="lie_stable",
    )
    pending = {
        "event": event,
        "pass_a": {
            "belief_state": "possible_harassment",
            "belief_p": 0.34,
            "light": "on",
            "mode": "silent_confirm",
        },
    }
    later = {"posture": "lie_stable", "motion_type": "none", "human_sound": "none"}
    return pass_b_input(pending, "no_new_event", later)


def sample_morning_input() -> dict:
    return morning_input(
        "n2",
        "habit: ~02:00 outcome_15min=left_bed x3 | motion_counts: sigh_shift x3 (±30min)",
        "n2 02:00 | motion_type: sigh_shift (torso) | outcome_15min: left_bed | first_light: off | correction: none | response_verdict: appropriate | morning_label: none",
        "none",
        "none",
    )
