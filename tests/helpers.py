"""Shared builders for module tests. Not product rules."""

from __future__ import annotations

import json

from nightguard.events import make_event
from nightguard.memory import make_card


def morning_json(filter_text: str, brief: str = "Local stand-in.") -> str:
    return json.dumps(
        {
            "brief": brief,
            "timeline": "none",
            "filter_text": filter_text,
        }
    )


def off_pass_a_json() -> str:
    return json.dumps(
        {
            "reasoning": "Low belief. Do not disturb.",
            "belief_state": "quiet",
            "belief_p": 0.2,
            "mode": "none",
        }
    )


def add_minutes(t: str, minutes: int) -> str:
    parts = t.split(":")
    h, m = int(parts[0]), int(parts[1])
    s = int(parts[2]) if len(parts) > 2 else 0
    total = (h * 60 + m + minutes) % 1440
    return f"{total // 60:02d}:{total % 60:02d}:{s:02d}"


def seed_card(**overrides) -> dict:
    event = make_event(
        night_id=overrides.pop("night_id", "n1"),
        t=overrides.pop("t", "02:00:00"),
        motion_type=overrides.pop("motion_type", "sigh_shift"),
        body_zone=overrides.pop("body_zone", "torso"),
        posture=overrides.pop("posture", "lie_stable"),
    )
    pass_a = {
        "reasoning": "seed",
        "belief_state": overrides.pop("belief_state", "quiet"),
        "belief_p": 0.2,
        "awake": False,
        "light": "off",
        "mode": "none",
        "brightness": "none",
        "duration_s": 0,
        "aim": "none",
    }
    pass_b = {
        "verdict": overrides.pop("verdict", "appropriate"),
        "revised_belief_p": 0.2,
        "reason": "seed outcome_15min later_posture later_motion_type",
    }
    return make_card(
        event=event,
        pass_a=pass_a,
        pass_b=pass_b,
        outcome_15min=overrides.pop("outcome_15min", "left_bed"),
        morning_label=overrides.pop("morning_label", "none"),
    )
